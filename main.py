from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
import uvicorn
from typing import List, Dict, Optional
import databases
import sqlalchemy
from pydantic import BaseModel
import uuid
import asyncio

# Database setup 
DATABASE_URL = "sqlite:///./cloud_access.db"
database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

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
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") # Placeholder for now


# Placeholder for OAuth2 authentication. Replace with actual implementation.
async def get_current_user(token: str = Depends(oauth2_scheme)):
     # Replace with your authentication logic
    return {"user_id": "admin"} if token == "admin_token" else {"user_id": token}


class Plan(BaseModel):
    name: str
    description: str
    api_permissions: List[str]
    usage_limits: Dict[str, int]  

class Permission(BaseModel):
    name: str
    api_endpoint: str
    description: str

class Subscription(BaseModel):
    plan_id: str


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
    query = plans.insert().values(id=str(uuid.uuid4()), **plan.dict())
    await database.execute(query)
    return plan


@app.get("/plans/{plan_id}", response_model=Plan)
async def get_plan(plan_id: str):
    query = plans.select().where(plans.c.id == plan_id)
    result = await database.fetch_one(query)
    if not result:
        raise HTTPException(status_code=404, detail="Plan not found")
    return Plan(**result)


@app.put("/plans/{plan_id}", response_model=Plan) # Admin function
async def modify_plan(plan_id: str, plan: Plan, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    query = plans.update().where(plans.c.id == plan_id).values(**plan.dict())
    await database.execute(query)
    return plan

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
    query = permissions.insert().values(id=str(uuid.uuid4()), **permission.dict())
    await database.execute(query)
    return permission


@app.put("/permissions/{permission_id}", response_model=Permission)  # Admin function
async def modify_permission(permission_id: str, permission: Permission, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    query = permissions.update().where(permissions.c.id == permission_id).values(**permission.dict())
    await database.execute(query)
    return permission


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

    query = subscriptions.insert().values(user_id=current_user["user_id"], plan_id=subscription.plan_id)
    await database.execute(query)
    return {"message": "Subscribed to plan"}


@app.get("/subscriptions/{user_id}", response_model=Subscription)
async def view_subscription_details(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id and current_user["user_id"] != "admin":  # Allow admin access
        raise HTTPException(status_code=403, detail="Forbidden")

    query = subscriptions.select().where(subscriptions.c.user_id == user_id)
    result = await database.fetch_one(query)
    if not result:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return Subscription(**result)



@app.get("/cloud_api/resource1")  
async def cloud_api_resource1(current_user: dict = Depends(get_current_user)):

    await track_usage(current_user["user_id"], "/cloud_api/resource1")  # Track usage
    return {"message": "Accessed resource1"}



#  Access Control
@app.get("/access/{user_id}/{api_request}")
async def check_access_permission(user_id: str, api_request: str, current_user: dict = Depends(get_current_user)):

    plan_id_query = subscriptions.select(subscriptions.c.plan_id).where(subscriptions.c.user_id == user_id)
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


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)