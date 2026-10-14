"""REST API Gateway (Fig 4 Layer 2): one NinjaAPI at /api/v1 with the 20 operations the frontend uses.

Route functions only validate, check permissions and call orchestration or domain selectors/services.
OpenAPI docs: /api/v1/docs
"""

from ninja import NinjaAPI

from . import errors
from .auth import BearerAuth
from .routers import assessments, auth, operations, requests, reviews, teaching, workspace

api = NinjaAPI(title="LingoPath API", version="1.0.0", urls_namespace="api_v1", auth=BearerAuth())
errors.install(api)

api.add_router("/auth", auth.router)
for module in (workspace, requests, assessments, reviews, teaching, operations):
    api.add_router("", module.router)
