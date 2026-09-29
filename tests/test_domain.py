from uuid import uuid4
import pytest

from nod.domain.models import validate_dependency
from nod.domain.errors import InvalidDependencyError


def test_self_dependency_is_rejected():
    value = uuid4()
    with pytest.raises(InvalidDependencyError):
        validate_dependency(value, value)
