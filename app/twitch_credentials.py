import logging
import sys
from typing import Literal

logger = logging.getLogger(__name__)

CREDENTIAL_TARGET_NAME = "TwitchPearSongRequests/TwitchOAuth"
CREDENTIAL_USERNAME = "TwitchBot"
TokenStatus = Literal["ok", "missing", "unsupported_platform", "import_failed", "read_failed"]

class TwitchCredentialStore:
    """Securely stores the Twitch OAuth token using Windows Credential Manager and Keyring."""

    @staticmethod
    def read_token() -> tuple[str | None, TokenStatus]:
        if sys.platform != "win32":
            return None, "unsupported_platform"

        token = TwitchCredentialStore._get_windows_credential()
        if token:
            return token, "ok"

        token = TwitchCredentialStore._get_keyring_credential()
        if token:
            return token, "ok"

        return None, "missing"

    @staticmethod
    def get_token() -> str | None:
        token, _ = TwitchCredentialStore.read_token()
        return token

    @staticmethod
    def set_token(token: str) -> None:
        if TwitchCredentialStore._set_windows_credential(token):
            logger.debug("Token securely written to Windows Credential Manager.")
            return
        if TwitchCredentialStore._set_keyring_credential(token):
            logger.debug("Token securely written to Keyring.")
            return
        logger.error("Failed to write token to any Credential Manager.")
        raise RuntimeError("No secure credential storage backend is available.")

    @staticmethod
    def delete_token() -> None:
        if TwitchCredentialStore._delete_windows_credential():
            logger.debug("Token removed from Windows Credential Manager.")
            return
        TwitchCredentialStore._delete_keyring_credential()
        logger.debug("Token removed from Keyring (if present).")

    @staticmethod
    def _get_windows_credential() -> str:
        if sys.platform != "win32":
            return ""
        try:
            import win32cred

            cred = win32cred.CredRead(CREDENTIAL_TARGET_NAME, win32cred.CRED_TYPE_GENERIC)
            blob = cred.get("CredentialBlob", b"")
            if isinstance(blob, bytes):
                token_str = blob.decode("utf-8", errors="ignore")
                return token_str.replace("\x00", "").strip()
            return str(blob or "").strip()
        except Exception as e:
            logger.debug(f"Failed to read from win32cred: {e}")
            return ""

    @staticmethod
    def _set_windows_credential(token: str) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import win32cred

            win32cred.CredWrite(
                {
                    "Type": win32cred.CRED_TYPE_GENERIC,
                    "TargetName": CREDENTIAL_TARGET_NAME,
                    "UserName": CREDENTIAL_USERNAME,
                    "CredentialBlob": token,
                    "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
                },
                0,
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to write to win32cred: {e}")
            return False

    @staticmethod
    def _delete_windows_credential() -> bool:
        if sys.platform != "win32":
            return False
        try:
            import win32cred

            win32cred.CredDelete(CREDENTIAL_TARGET_NAME, win32cred.CRED_TYPE_GENERIC, 0)
            return True
        except Exception as e:
            logger.debug(f"Failed to delete from win32cred: {e}")
            return False

    @staticmethod
    def _get_keyring_credential() -> str:
        try:
            import keyring

            return keyring.get_password(CREDENTIAL_TARGET_NAME, CREDENTIAL_USERNAME) or ""
        except Exception as e:
            logger.debug(f"Failed to read from keyring: {e}")
            return ""

    @staticmethod
    def _set_keyring_credential(token: str) -> bool:
        try:
            import keyring

            keyring.set_password(CREDENTIAL_TARGET_NAME, CREDENTIAL_USERNAME, token)
            return True
        except Exception as e:
            logger.debug(f"Failed to write to keyring: {e}")
            return False

    @staticmethod
    def _delete_keyring_credential() -> None:
        try:
            import keyring

            keyring.delete_password(CREDENTIAL_TARGET_NAME, CREDENTIAL_USERNAME)
        except Exception as e:
            logger.debug(f"Failed to delete from keyring: {e}")
            pass
