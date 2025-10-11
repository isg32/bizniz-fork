# app/core/decorators.py

from functools import wraps
from fastapi import HTTPException, status
from app.services.internal import pocketbase_service
from app.schemas.user import User as UserSchema

# MODIFICATION 1: Add 'description' to the decorator's arguments.
def require_coins(cost: float, description: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user: UserSchema = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials",
                )

            # 1. Pre-execution check
            user_record = pocketbase_service.get_user_by_id(current_user.id)
            if not user_record or user_record.coins < cost:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=f"Insufficient coins. This action requires {cost} coins, but you have {user_record.coins if user_record else 0}.",
                )

            # 2. Execute the actual endpoint function
            try:
                result = await func(*args, **kwargs)
            except Exception as e:
                print(f"Service call failed for user {current_user.id}. No coins were burned. Error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="The external service failed to process the request. You have not been charged."
                ) from e

            # 3. Post-execution action: Burn coins
            # MODIFICATION 2: Pass the 'description' to the burn_coins function.
            success, message = pocketbase_service.burn_coins(current_user.id, cost, description)
            if not success:
                print(f"CRITICAL: FAILED to burn {cost} coins for user {current_user.id} after successful service call. Reason: {message}")
            
            # Add updated coin balance to the response
            if isinstance(result, dict):
                 updated_user_record = pocketbase_service.get_user_by_id(current_user.id)
                 result["coins_burned"] = cost
                 result["new_coin_balance"] = updated_user_record.coins if updated_user_record else "unknown"

            return result
        return wrapper
    return decorator