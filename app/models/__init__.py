# app/models/__init__.py
# This file makes the directory a Python package
# It's important to import the models in the right order
# to avoid circular import errors

# First, import models that don't depend on other models
from app.models.setting import Setting
from app.models.tag import Tag
from app.models.audit import AuditLog
from app.models.group import Group, Permission
from app.models.notification import NotificationSetting, NotificationLog
# Then import models that depend on others
from app.models.user import User

# Finally, import models that depend on User
from app.models.asset import Asset, AssetFile# This file makes the directory a Python package
