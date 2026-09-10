import importlib.metadata

import grpc
import gpsoauth
from google.protobuf import __version__ as protobuf_version
from notebooklm import NotebookLMClient


def main() -> None:
    ctx = NotebookLMClient.from_storage(profile="default", backend="android")
    # Construction must remain lazy: this probe intentionally never enters the
    # async context and therefore performs no credential or network I/O.
    print(
        {
            "notebooklm_py": importlib.metadata.version("notebooklm-py"),
            "grpcio": grpc.__version__,
            "protobuf": protobuf_version,
            "gpsoauth_import": bool(gpsoauth),
            "android_context_constructed": ctx is not None,
        }
    )


if __name__ == "__main__":
    main()
