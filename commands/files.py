"""File operations that can only touch approved folders.

Allowed by default: Desktop, Documents, Downloads, Pictures, Music, Videos
(inside your user profile, including their OneDrive versions), plus anything
you list in ALLOWED_FOLDERS in .env.

Rules enforced here, whatever the AI asks for:
  - every path is resolved (.., shortcuts and symlinks included) and must end up
    inside an allowed folder
  - programs and scripts can never be created or opened (.exe, .bat, .ps1 ...)
  - nothing is overwritten or moved over an existing file without a yes
  - deleting sends to the Recycle Bin, needs ALLOW_FILE_DELETION=true and a yes
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

STANDARD_FOLDERS = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")

# Never created, written or opened by Jarvis: these can run code.
BLOCKED_EXTENSIONS = {
    ".exe", ".com", ".bat", ".cmd", ".msi", ".msp", ".ps1", ".psm1", ".psd1", ".vbs", ".vbe",
    ".js", ".jse", ".wsf", ".wsh", ".hta", ".scr", ".cpl", ".reg", ".lnk", ".url", ".dll",
    ".sys", ".jar", ".py", ".pyw", ".sh", ".appref-ms", ".gadget", ".inf", ".pif", ".msc",
}
# The only kinds of file Jarvis will write or read as text.
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log", ".html", ".htm", ".xml", ".rtf", ".ini", ".yaml", ".yml"}

MAX_WRITE_CHARS = 20_000
MAX_READ_CHARS = 3_000
MAX_LIST = 30
MAX_COPY_BYTES = 500 * 1024 * 1024
SEARCH_SECONDS = 4.0


class FileError(ValueError):
    """A message safe to speak to the user."""


class FileTools:
    def __init__(self, extra_folders: tuple[str, ...] = (), home: Path | None = None,
                 allow_delete: bool = False):
        self.home = Path(home) if home else Path.home()
        self.allow_delete = allow_delete
        self.roots: dict[str, Path] = {}
        self._discover(extra_folders)

    # ---- folders --------------------------------------------------------

    def _discover(self, extra_folders) -> None:
        bases = [self.home]
        for name in ("OneDrive",):
            candidate = self.home / name
            if candidate.is_dir():
                bases.append(candidate)
        for name in STANDARD_FOLDERS:
            for base in bases:
                folder = base / name
                if folder.is_dir():
                    self.roots.setdefault(name.lower(), folder.resolve())
        for extra in extra_folders:
            path = Path(os.path.expandvars(extra)).expanduser()
            if path.is_dir():
                self.roots.setdefault(path.name.lower(), path.resolve())

    def describe_roots(self) -> str:
        return ", ".join(self.roots) if self.roots else "none found"

    # ---- path safety ----------------------------------------------------

    def resolve(self, text: str, *, must_exist: bool = False) -> Path:
        text = (text or "").strip().strip('"').strip("'")
        if not text:
            raise FileError("I need a file or folder name.")
        text = text.replace("\\", "/")
        parts = [p for p in text.split("/") if p not in ("", ".")]

        if text.startswith("~"):
            path = Path(os.path.expanduser(text))
        elif len(text) > 1 and text[1] == ":" or text.startswith("/"):
            path = Path(text)                                   # absolute
        elif parts and parts[0].lower() in self.roots:
            path = self.roots[parts[0].lower()].joinpath(*parts[1:])
        elif "documents" in self.roots:
            path = self.roots["documents"].joinpath(*parts)    # bare name -> Documents
        else:
            raise FileError("I couldn't find your Documents folder.")

        try:
            path = path.resolve()
        except (OSError, RuntimeError) as error:
            raise FileError("That path isn't valid.") from error
        if not self._inside_roots(path):
            raise FileError("I'm only allowed to use your Desktop, Documents, Downloads, "
                            "Pictures, Music and Videos folders.")
        if path in self.roots.values():
            return path  # the folder itself is fine for listing/opening
        if must_exist and not path.exists():
            raise FileError("I couldn't find that.")
        return path

    def _inside_roots(self, path: Path) -> bool:
        return any(path == root or root in path.parents for root in self.roots.values())

    @staticmethod
    def _check_extension(path: Path, *, text_only: bool = False) -> None:
        ext = path.suffix.lower()
        if ext in BLOCKED_EXTENSIONS:
            raise FileError(f"I never create or open {ext} files because they can run code.")
        if text_only and ext not in TEXT_EXTENSIONS:
            raise FileError("I can only write plain text files such as .txt, .md or .csv.")

    # ---- tools ----------------------------------------------------------

    def list_folder(self, args: dict) -> str:
        path = self.resolve(args["path"], must_exist=True)
        if not path.is_dir():
            return "That is a file, not a folder."
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        entries = [e for e in entries if not e.name.startswith(".")]
        shown = [f"{e.name}{'/' if e.is_dir() else ''}" for e in entries[:MAX_LIST]]
        more = f" (and {len(entries) - MAX_LIST} more)" if len(entries) > MAX_LIST else ""
        return f"{path} has {len(entries)} items: " + (", ".join(shown) or "nothing") + more

    def search_files(self, args: dict) -> str:
        words = [w for w in args["query"].lower().split() if w]
        if not words:
            return "Tell me what file name to look for."
        if args.get("folder"):
            starts = [self.resolve(args["folder"], must_exist=True)]
        else:
            starts = list(self.roots.values())
        deadline = time.monotonic() + SEARCH_SECONDS
        found: list[Path] = []
        for start in starts:
            for dirpath, dirnames, filenames in os.walk(start):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                depth = len(Path(dirpath).relative_to(start).parts)
                if depth >= 5:
                    dirnames[:] = []
                for name in filenames + dirnames:
                    low = name.lower()
                    if all(w in low for w in words):
                        found.append(Path(dirpath) / name)
                        if len(found) >= 10:
                            break
                if len(found) >= 10 or time.monotonic() > deadline:
                    break
            if len(found) >= 10 or time.monotonic() > deadline:
                break
        if not found:
            return "I found no files or folders matching that."
        return f"Found {len(found)}: " + "; ".join(str(p) for p in found)

    def open_path(self, args: dict) -> str:
        path = self.resolve(args["path"], must_exist=True)
        if path.is_file():
            self._check_extension(path)
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]  # Windows only
        except AttributeError:
            return "Opening files only works on Windows."
        except OSError:
            return "Windows couldn't open that."
        return f"Opening {path.name}."

    def create_folder(self, args: dict) -> str:
        path = self.resolve(args["path"])
        if path.exists():
            return f"{path.name} already exists."
        path.mkdir(parents=True)
        return f"Created the folder {path.name}."

    def confirm_write(self, args: dict) -> str | None:
        try:
            path = self.resolve(args["path"])
        except FileError:
            return None  # the handler will report the real problem
        if path.exists() and not args.get("append"):
            return f"{path.name} already exists. Replace it?"
        return None

    def write_text_file(self, args: dict) -> str:
        path = self.resolve(args["path"])
        self._check_extension(path, text_only=True)
        content = args["content"]
        if len(content) > MAX_WRITE_CHARS:
            raise FileError("That is too much text to write at once.")
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if args.get("append") else "w"
        with open(path, mode, encoding="utf-8") as handle:
            handle.write(content)
        return f"{'Added to' if mode == 'a' else 'Saved'} {path.name}."

    def read_text_file(self, args: dict) -> str:
        path = self.resolve(args["path"], must_exist=True)
        if not path.is_file():
            return "That is a folder, not a file."
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            raise FileError("I can only read plain text files.")
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(MAX_READ_CHARS + 1)
        suffix = " [shortened]" if len(text) > MAX_READ_CHARS else ""
        return text[:MAX_READ_CHARS] + suffix

    def copy_path(self, args: dict) -> str:
        src = self.resolve(args["source"], must_exist=True)
        dst = self.resolve(args["destination"])
        if not src.is_file():
            raise FileError("I can copy single files only.")
        self._check_extension(src)
        if dst.is_dir():
            dst = dst / src.name
        if dst.exists():
            raise FileError(f"{dst.name} already exists there, so I didn't copy over it.")
        if src.stat().st_size > MAX_COPY_BYTES:
            raise FileError("That file is too large for me to copy.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return f"Copied {src.name} to {dst.parent.name}."

    def confirm_move(self, args: dict) -> str | None:
        try:
            src = self.resolve(args["source"])
            dst = self.resolve(args["destination"])
        except FileError:
            return None
        return f"Move {src.name} to {dst.parent.name if not dst.is_dir() else dst.name}?"

    def move_path(self, args: dict) -> str:
        src = self.resolve(args["source"], must_exist=True)
        dst = self.resolve(args["destination"])
        if src in self.roots.values():
            raise FileError("I won't move one of your main folders.")
        if src.is_file():
            self._check_extension(src)
        if dst.is_dir():
            dst = dst / src.name
        if dst.exists():
            raise FileError(f"{dst.name} already exists there, so I didn't move over it.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved {src.name} to {dst.parent.name}."

    def confirm_delete(self, args: dict) -> str | None:
        try:
            path = self.resolve(args["path"], must_exist=True)
        except FileError:
            return None
        kind = "folder" if path.is_dir() else "file"
        return f"Move the {kind} {path.name} to the Recycle Bin?"

    def delete_path(self, args: dict) -> str:
        path = self.resolve(args["path"], must_exist=True)
        if path in self.roots.values():
            raise FileError("I won't delete one of your main folders.")
        try:
            from send2trash import send2trash
        except ImportError:
            return "Deleting needs send2trash. Run: python -m pip install send2trash"
        send2trash(str(path))
        return f"Moved {path.name} to the Recycle Bin."
