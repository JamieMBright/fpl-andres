"""Server-side persistence for FPL Andres.

Every table in the schema has forced row-level security with no policy, so these
writers only work with the service-role secret key and only ever run server
side. Nothing here may be imported by browser-bound code.
"""

from fpl_andres.persistence.supabase import (
    MissingCredentialsError,
    SupabaseCredentials,
    SupabaseRestClient,
    SupabaseWriteError,
)
from fpl_andres.persistence.workflow import WorkflowRun, WorkflowRunRecorder

__all__ = [
    "MissingCredentialsError",
    "SupabaseCredentials",
    "SupabaseRestClient",
    "SupabaseWriteError",
    "WorkflowRun",
    "WorkflowRunRecorder",
]
