import collections
import os
import time
import datetime
from urllib.parse import parse_qs

import requests


class GitHubAPISession(requests.Session):
    def __init__(self, token=None):
        super().__init__()
        token = self.get_token()
        self.headers.update({"Authorization": f"Bearer {token}"})

    def get_token(self):
        token = os.environ.get("GITHUB_WORKFLOW_RUNS_TOKEN")
        expiry = os.environ.get("GITHUB_WORKFLOW_RUNS_TOKEN_EXPIRY")
        if token and not expiry:
            # This is a PAT provided by the user.
            return token
        elif (
            token
            and expiry
            and datetime.datetime.fromisoformat(expiry) > datetime.datetime.now()
        ):
            return token
        else:
            return self._refresh_github_app_user_access_token()

    def _refresh_github_app_user_access_token(self):
        # Let the KeyError get raised if there is no client ID,
        # as either this should be set, or the user should provide their own token.
        app_auth = GitHubAppAuthentication(os.environ["GITHUB_APP_CLIENT_ID"])
        token, expiry = app_auth.get_user_access_token()
        replace_value_in_dotenv("GITHUB_WORKFLOW_RUNS_TOKEN", token)
        replace_value_in_dotenv("GITHUB_WORKFLOW_RUNS_TOKEN_EXPIRY", expiry.isoformat())
        return token


def replace_value_in_dotenv(key, value):
    lines = []
    for line in open(".env", "r").readlines():
        if not line.startswith(f"{key}="):
            lines.append(line)
    lines.append(f"{key}={value}\n")
    with open(".env", "w") as f:
        f.writelines(lines)


class GitHubAppAuthentication:
    LoginResponse = collections.namedtuple(
        "LoginResponse",
        [
            "device_code",
            "user_code",
            "verification_uri",
            "expires_in",
            "interval",
        ],
    )

    def __init__(self, app_client_id):
        self.app_client_id = app_client_id

    def post_login_request(self):
        response = requests.post(
            "https://github.com/login/device/code",
            data={
                "client_id": self.app_client_id,
            },
        )
        response.raise_for_status()
        response_data = parse_qs(response.text)
        return self.LoginResponse(
            device_code=response_data["device_code"][0],
            user_code=response_data["user_code"][0],
            verification_uri=response_data["verification_uri"][0],
            expires_in=int(response_data["expires_in"][0]),
            interval=int(response_data["interval"][0]),
        )

    def post_oauth_request(self, device_code):
        response = requests.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": self.app_client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )

        return response

    def ask_user_to_authorize_device(self, login):
        input(
            f"Please go to {login.verification_uri} and enter the code: {login.user_code}\n"
            f"This code will expire in {login.expires_in // 60} minutes {login.expires_in % 60} seconds.\n"
            f"Press any key to continue after you have authorized the app."
        )

    def get_user_access_token(self):
        login = self.post_login_request()
        timeout_time = time.time() + login.expires_in
        self.ask_user_to_authorize_device(login)
        while time.time() < timeout_time:
            response = self.post_oauth_request(login.device_code)
            if response.status_code == 200:
                qs = parse_qs(response.text)
                access_token = qs["access_token"][0]
                expires_in = int(qs["expires_in"][0])
                return (
                    access_token,
                    datetime.datetime.now() + datetime.timedelta(seconds=expires_in),
                )
            time.sleep(login.interval + 1)
