# Stage 7: App launching and voice typing

Install the additional desktop-control dependencies from the project folder:

```powershell
python -m pip install -r requirements.txt
```

Examples (say after the wake phrase, or type these into the assistant's console):

- `open Paint`
- `open Microsoft Word`
- `open Visual Studio Code`
- `type: Hello, this is a voice typing test.`
- `type in Notepad: Hello from Jarvis.`

General app launching searches the current user's and all-users' Windows Start Menu shortcuts. It cannot guarantee discovery of portable apps, apps without shortcuts, or every packaged Windows app. Add a Start Menu shortcut for apps that cannot be found.

For `type: ...`, click the intended target window before speaking the command. For `type in Notepad: ...`, Notepad must already be open; Jarvis tries to bring its window to the foreground. Text is pasted through the clipboard, which supports punctuation and Unicode better than simulated keystrokes.

Typing is an actual computer action. Review the target window before dictating private or sensitive text. This does not bypass administrator prompts, secure desktop restrictions, or app-specific protections.
