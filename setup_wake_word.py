"""Download openWakeWord's bundled models once while online."""

try:
    import openwakeword
except ImportError as error:
    raise SystemExit(
        "openWakeWord is not installed. Run: pip install openwakeword"
    ) from error

print("Downloading openWakeWord model files. This needs an internet connection the first time...")
openwakeword.utils.download_models()
print("Download finished. Wake-word detection runs locally after the model is available.")
