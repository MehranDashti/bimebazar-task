import pytest

from app.tests.factories import example_payload, user_payload


@pytest.fixture
def new_user_payload():
    return user_payload()


@pytest.fixture
def new_example_payload():
    return example_payload()
