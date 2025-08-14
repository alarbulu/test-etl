import collections
import os
import time
from urllib.parse import parse_qs

import requests


class GitHubAPISession(requests.Session):
    def __init__(self, token=None):
        super().__init__()
        token = self._get_token()
        self.headers.update({"Authorization": f"Bearer {token}"})
        self.params.update({"per_page": 100, "format": "json"})

    def _get_token(self):
        try:
            return os.environ["GITHUB_WORKFLOW_RUNS_TOKEN"]
        except KeyError:
            return get_token(os.environ["GITHUB_APP_CLIENT_ID"])


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


def post_login_request(app_client_id):
    response = requests.post(
        "https://github.com/login/device/code",
        data={
            "client_id": app_client_id,
        },
    )
    response.raise_for_status()
    response_data = parse_qs(response.text)
    return LoginResponse(
        device_code=response_data["device_code"][0],
        user_code=response_data["user_code"][0],
        verification_uri=response_data["verification_uri"][0],
        expires_in=int(response_data["expires_in"][0]),
        interval=int(response_data["interval"][0]),
    )


def get_token(app_client_id):
    login = post_login_request(app_client_id)
    timeout_time = time.time() + login.expires_in

    input(
        f"Please go to {login.verification_uri} and enter the code: {login.user_code}\n"
        f"This code will expire in {login.expires_in} seconds.\n"
        f"Press any key to continue after you have authorized the app."
    )
    while time.time() < timeout_time:
        response = requests.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": app_client_id,
                "device_code": login.device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        if response.status_code == 200:
            (access_token,) = parse_qs(response.text)["access_token"]
            return access_token
        time.sleep(login.interval + 1)
