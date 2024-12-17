from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
import uvicorn
from typing import List, Dict, Optional
import databases
import sqlalchemy
from pydantic import BaseModel
import uuid
import asyncio
import logging
from sqlalchemy import literal

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup 
DATABASE_URL = "sqlite:///./cloud_access.db"
database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

#Table info
plans = sqlalchemy.Table(
    "plans",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.String, primary_key=True),
    sqlalchemy.Column("name", sqlalchemy.String),
    sqlalchemy.Column("description", sqlalchemy.String),
    sqlalchemy.Column("api_permissions", sqlalchemy.JSON), # Store as JSON
    sqlalchemy.Column("usage_limits", sqlalchemy.JSON),    # Store as JSON
)

permissions = sqlalchemy.Table(
    "permissions",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.String, primary_key=True),
    sqlalchemy.Column("name", sqlalchemy.String),
    sqlalchemy.Column("api_endpoint", sqlalchemy.String),
    sqlalchemy.Column("description", sqlalchemy.String),
)

subscriptions = sqlalchemy.Table(
    "subscriptions",
    metadata,
    sqlalchemy.Column("user_id", sqlalchemy.String, primary_key=True),
    sqlalchemy.Column("plan_id", sqlalchemy.String),  # Foreign key to plans table
    sqlalchemy.Column("requests_used", sqlalchemy.Integer, default=0)
)

usage = sqlalchemy.Table(
    "usage",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("user_id", sqlalchemy.String),
    sqlalchemy.Column("api_endpoint", sqlalchemy.String),
    sqlalchemy.Column("count", sqlalchemy.Integer, default=0),
)

engine = sqlalchemy.create_engine(DATABASE_URL)
metadata.create_all(engine)


app = FastAPI()

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Cloud Access Management System"}

@app.get("/favicon.ico")
async def favicon():
    return {"message": "Favicon not implemented"}


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") # Placeholder for now

# Placeholder for OAuth2 authentication. Replace with actual implementation.
async def get_current_user(token: str = Depends(oauth2_scheme)):
     # Replace with your authentication logic
    return {"user_id": "admin"} if token == "admin_token" else {"user_id": token}

#pydantic models
class Plan(BaseModel):
    id: Optional[str] = None
    name: str
    description: str
    api_permissions: List[str]
    usage_limits: Dict[str, int]  

class Permission(BaseModel):
    id: Optional[str] = None
    name: str
    api_endpoint: str
    description: str

class Subscription(BaseModel):
    plan_id: str
    requests_used: Optional[int] = 0


class UsageData(BaseModel):
    api_endpoint: str


@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.post("/plans", response_model=Plan) # Admin function
async def create_plan(plan: Plan, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != "admin":
         raise HTTPException(status_code=403, detail="Forbidden")

    plan_id = str(uuid.uuid4())
    plan_data = plan.dict(exclude={'id'})

    query = plans.insert().values(id=plan_id, **plan_data)
    await database.execute(query)
    
    return {**plan_data, "id": plan_id}



@app.get("/plans/{plan_id}", response_model=Plan)
async def get_plan(plan_id: str):
    print(f"Searching for id: {plan_id}")
    query = plans.select().where(plans.c.id == plan_id)
    plan = await database.fetch_one(query)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@app.put("/plans/{plan_id}", response_model=Plan) # Admin function
async def modify_plan(plan_id: str, plan: Plan, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    plan_data = plan.dict(exclude_unset=True, exclude={'id'})

    query = plans.update().where(plans.c.id == plan_id).values(plan_data)
    await database.execute(query)

    updated_plan_query = plans.select().where(plans.c.id == plan_id)
    updated_plan = await database.fetch_one(updated_plan_query)

    return updated_plan

@app.delete("/plans/{plan_id}") # Admin function
async def delete_plan(plan_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    query = plans.delete().where(plans.c.id == plan_id)
    await database.execute(query)
    return {"message": "Plan deleted"}



# Permission Management
@app.post("/permissions", response_model=Permission) # Admin function
async def create_permission(permission: Permission, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    permission_id = str(uuid.uuid4())
    permission_data = permission.dict(exclude={'id'})

    query = permissions.insert().values(id=permission_id, **permission_data)
    await database.execute(query)

    return {**permission_data, "id": permission_id}


@app.put("/permissions/{permission_id}", response_model=Permission)  # Admin function
async def modify_permission(permission_id: str, permission: Permission, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    permission_data = permission.dict(exclude={'id'})

    query = permissions.update().where(permissions.c.id == permission_id).values(permission_data)
    await database.execute(query)

    updated_permission_query = permissions.select().where(permissions.c.id == permission_id)
    updated_permission = await database.fetch_one(updated_permission_query)

    return updated_permission


@app.delete("/permissions/{permission_id}") # Admin function
async def delete_permission(permission_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    query = permissions.delete().where(permissions.c.id == permission_id)
    await database.execute(query)
    return {"message": "Permission deleted"}


# User Subscription Handling
@app.post("/subscriptions")  # Customer function
async def subscribe_to_plan(subscription: Subscription, current_user: dict = Depends(get_current_user)):

    user_id = current_user["user_id"]

    existing_subscription = await database.fetch_one(subscriptions.select().where(subscriptions.c.user_id == user_id))

    if existing_subscription:
        query = subscriptions.update().where(subscriptions.c.user_id == user_id).values(plan_id=subscription.plan_id, requests_used=subscriptions.c.requests_used + 1)
        await database.execute(query)
        return {"message": f"User {user_id} updated to plan {subscription.plan_id}"}

    query = subscriptions.insert().values(user_id=user_id, plan_id=subscription.plan_id, requests_used=subscriptions.c.requests_used + 1)
    await database.execute(query)

    return {"message": f"User {user_id} subscribed to plan {subscription.plan_id}"}


@app.get("/subscriptions/{user_id}", response_model=Subscription)
async def view_subscription_details(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id and current_user["user_id"] != "admin":  # Allow admin access
        raise HTTPException(status_code=403, detail="Forbidden")

    query = subscriptions.select().where(subscriptions.c.user_id == user_id)
    result = await database.fetch_one(query)
    if not result:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return Subscription(**result)

@app.get("/subscriptions/{user_id}/usage")
async def view_usage_details(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    query = subscriptions.select().where(subscriptions.c.user_id == user_id)
    result = await database.fetch_one(query)

    if not result:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    usage_statistics = {
        "user_id": result["user_id"],
        "plan_id":result["plan_id"],
        "requests_used": result["requests_used"] if "requests_used" in result.keys() else 0,
    }

    print(dict(result))
    
    return usage_statistics

@app.put("/subscriptions/{user_id}")  # Customer function
async def subscribe_to_plan(subscription: Subscription, current_user: dict = Depends(get_current_user)):

    user_id = current_user["user_id"]

    existing_subscription = await database.fetch_one(subscriptions.select().where(subscriptions.c.user_id == user_id))

    if existing_subscription:
        query = subscriptions.update().where(subscriptions.c.user_id == user_id).values(plan_id=subscription.plan_id, requests_used=subscriptions.c.requests_used + 1)
        await database.execute(query)
        return {"message": f"User {user_id} updated to plan {subscription.plan_id}"}

# @app.get("/subscriptions/{user_id}")

@app.get("/cloud_api/resource1")  
async def cloud_api_resource1(current_user: dict = Depends(get_current_user)):

    await track_usage(current_user["user_id"], "/cloud_api/resource1")  # Track usage
    return {"message": "Accessed resource1"}


#  Access Control
@app.get("/access/{user_id}/{api_request}")
async def check_access_permission(user_id: str, api_request: str, current_user: dict = Depends(get_current_user)):

    plan_id_query = subscriptions.select().where(subscriptions.c.user_id == user_id)
    plan_id_result = await database.fetch_one(plan_id_query)

    if not plan_id_result:
        raise HTTPException(status_code=403, detail="No subscription found for this user")
    plan_id = plan_id_result["plan_id"]

    # Fetch plan details to check permissions and usage limits
    plan_query = plans.select().where(plans.c.id == plan_id)
    plan = await database.fetch_one(plan_query)

    if not plan:
        raise HTTPException(status_code=403, detail="Invalid subscription plan")

    permissions = plan["api_permissions"]
    if api_request not in permissions:
        raise HTTPException(status_code=403, detail="API access denied: Not in plan permissions")


    #check if limit is exceeded
    usage_limit = plan["usage_limits"].get(api_request)  # Get the limit for this specific API
    if usage_limit is not None:  # Only check if a limit is defined for this API
        usage_count = await get_usage_count(user_id, api_request)
        if usage_count >= usage_limit:
             raise HTTPException(status_code=429, detail="API access denied: Usage limit exceeded")

    return {"message": "Access granted"}




# Usage Tracking and Limit Enforcement
async def track_usage(user_id: str, api_endpoint: str):

    query = usage.update().where((usage.c.user_id == user_id) & (usage.c.api_endpoint == api_endpoint)).values(count=usage.c.count + 1)
    result = await database.execute(query)

    if result == 0:
        # No existing entry; insert a new one.
         query = usage.insert().values(user_id=user_id, api_endpoint=api_endpoint, count=1)
         await database.execute(query)


async def get_usage_count(user_id: str, api_endpoint: str):

    query = usage.select().where((usage.c.user_id == user_id) & (usage.c.api_endpoint == api_endpoint))
    result = await database.fetch_one(query)
    return result["count"] if result else 0


@app.post("/usage/{user_id}")
async def track_api_request(user_id: str, usage: UsageData):
    try:
        await track_usage(user_id, usage.api_endpoint)
        return {"message": "API request tracked successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/usage/{user_id}/limit")
async def check_limit_status(user_id: str, api_endpoint: str, current_user: dict = Depends(get_current_user)):
    # Fetch the user's plan and check the API permissions
    plan_id_query = subscriptions.select().where(subscriptions.c.user_id == user_id)
    plan_id_result = await database.fetch_one(plan_id_query)
    
    if not plan_id_result:
        raise HTTPException(status_code=403, detail="No subscription found for this user")
    
    plan_id = plan_id_result["plan_id"]

    # Fetch plan details to check limits
    plan_query = plans.select().where(plans.c.id == plan_id)
    plan = await database.fetch_one(plan_query)

    if not plan:
        raise HTTPException(status_code=403, detail="Invalid subscription plan")

    permissions = plan["api_permissions"]
    if api_endpoint not in permissions:
        raise HTTPException(status_code=403, detail="API access denied: Not in plan permissions")
    
    usage_limit = plan["usage_limits"].get(api_endpoint)
    if usage_limit is None:
        raise HTTPException(status_code=404, detail="No usage limit set for this endpoint in the plan")
    
    usage_count = await get_usage_count(user_id, api_endpoint)
    
    return {
        "api_endpoint": api_endpoint,
        "usage_count": usage_count,
        "limit": usage_limit,
        "status": "limit exceeded" if usage_count >= usage_limit else "under limit"
    }


#some apis
@app.get("/cloud_api/object_storage")
async def object_storage(current_user: dict = Depends(get_current_user)):  
    await track_usage(current_user["user_id"], "/cloud_api/object_storage")
    return {"message": "Accessed Object Storage"}


@app.post("/cloud_api/image_processing/resize")
async def image_resize(current_user: dict = Depends(get_current_user)):
    await track_usage(current_user["user_id"], "/cloud_api/image_processing/resize")
    return {"message": "Image Resized"}


@app.get("/cloud_api/database/query")
async def database_query(current_user: dict = Depends(get_current_user)):
    await track_usage(current_user["user_id"], "/cloud_api/database/query")
    return {"message": "Database Query Executed"}


@app.post("/cloud_api/machine_learning/sentiment_analysis")
async def sentiment_analysis(current_user: dict = Depends(get_current_user)):
    await track_usage(current_user["user_id"], "/cloud_api/machine_learning/sentiment_analysis")
    return {"message": "Sentiment Analysis Performed"}


@app.get("/cloud_api/file_conversion/pdf_to_docx")
async def file_conversion(current_user: dict = Depends(get_current_user)):
    await track_usage(current_user["user_id"], "/cloud_api/file_conversion/pdf_to_docx")
    return {"message": "File Converted"}

@app.post("/cloud_api/video_processing/transcribe")
async def transcribe_video(current_user: dict = Depends(get_current_user)):
   await track_usage(current_user["user_id"], "/cloud_api/video_processing/transcribe")
   return {"message": "Video transcribed"}

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)