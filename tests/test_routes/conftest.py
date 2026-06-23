import pytest

from tests.factories import user_payload


@pytest.fixture
def new_user_payload():
    return user_payload()
