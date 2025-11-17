"""
Payment service for Telegram Stars monetization.

Handles:
- Creating subscription tiers (FREE, PRO, ENTERPRISE)
- Processing Telegram Stars payments
- Webhook handling for successful payments
- Subscription management and renewal
- Usage tracking per tier
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from enum import Enum

from telegram import Update, LabeledPrice, ShippingOption
from telegram.ext import ContextTypes
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.models.database import Subscription, Payment, User

logger = logging.getLogger(__name__)


class SubscriptionTier(Enum):
    """Available subscription tiers."""
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class TierConfig:
    """Configuration for each subscription tier."""
    
    TIERS = {
        SubscriptionTier.FREE: {
            "name": "Free Plan",
            "price_in_stars": 0,
            "summaries_per_month": 5,
            "max_context_messages": 50,
            "features": [
                "5 summaries per month",
                "Basic sentiment analysis",
                "Community support",
            ],
            "description": "Perfect for personal use",
        },
        SubscriptionTier.PRO: {
            "name": "Pro Plan",
            "price_in_stars": 99,  # ~$0.99
            "summaries_per_month": 100,
            "max_context_messages": 500,
            "features": [
                "100 summaries per month",
                "Advanced AI analysis",
                "Priority processing",
                "Email support",
                "Custom summaries",
            ],
            "description": "For active group managers",
        },
        SubscriptionTier.ENTERPRISE: {
            "name": "Enterprise Plan",
            "price_in_stars": 299,  # ~$2.99
            "summaries_per_month": 1000,
            "max_context_messages": 2000,
            "features": [
                "Unlimited summaries",
                "Advanced AI analysis",
                "Real-time processing",
                "Priority support",
                "API access",
                "Custom integrations",
            ],
            "description": "For large organizations",
        },
    }

    @classmethod
    def get_tier_config(cls, tier: SubscriptionTier) -> Dict[str, Any]:
        """Get configuration for a tier."""
        return cls.TIERS.get(tier, cls.TIERS[SubscriptionTier.FREE])

    @classmethod
    def get_telegram_prices(cls) -> list:
        """Get prices for Telegram payment."""
        return [
            LabeledPrice(
                label=cls.TIERS[SubscriptionTier.PRO]["name"],
                amount=cls.TIERS[SubscriptionTier.PRO]["price_in_stars"],
            ),
            LabeledPrice(
                label=cls.TIERS[SubscriptionTier.ENTERPRISE]["name"],
                amount=cls.TIERS[SubscriptionTier.ENTERPRISE]["price_in_stars"],
            ),
        ]


class PaymentService:
    """Service for handling payments and subscriptions."""

    async def get_or_create_subscription(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> Subscription:
        """Get existing subscription or create FREE tier."""
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        result = await session.execute(stmt)
        subscription = result.scalar_one_or_none()

        if not subscription:
            # Create FREE tier subscription
            subscription = Subscription(
                user_id=user_id,
                tier=SubscriptionTier.FREE.value,
                price_in_stars=0,
                summaries_per_month=TierConfig.TIERS[SubscriptionTier.FREE]["summaries_per_month"],
                summaries_used_this_month=0,
                auto_renew=True,
            )
            subscription.reset_monthly_limit()
            session.add(subscription)
            await session.flush()
            logger.info(f"Created FREE subscription for user {user_id}")

        return subscription

    async def get_subscription(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> Optional[Subscription]:
        """Get user's subscription."""
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def can_generate_summary(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> tuple[bool, str]:
        """Check if user can generate a summary based on subscription."""
        subscription = await self.get_subscription(session, user_id)
        
        if not subscription:
            subscription = await self.get_or_create_subscription(session, user_id)

        # Check if subscription is active
        if not subscription.is_active():
            return False, "❌ Your subscription has expired. Please renew to continue."

        # Check monthly limit
        if subscription.summaries_used_this_month >= subscription.summaries_per_month:
            remaining_days = subscription.days_until_expiry() or 30
            return (
                False,
                f"⏱️ You've reached your monthly limit of {subscription.summaries_per_month} summaries. "
                f"Your limit resets in {remaining_days} days or upgrade your plan.",
            )

        return True, "✅ Subscription active"

    async def use_summary(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> bool:
        """Increment summary usage for user."""
        subscription = await self.get_subscription(session, user_id)
        
        if not subscription:
            subscription = await self.get_or_create_subscription(session, user_id)

        # Check if we need to reset monthly limit
        if (
            subscription.summaries_reset_at
            and subscription.summaries_reset_at < datetime.utcnow()
        ):
            subscription.reset_monthly_limit()

        subscription.summaries_used_this_month += 1
        await session.flush()
        logger.info(f"User {user_id} used summary: {subscription.summaries_used_this_month}/{subscription.summaries_per_month}")
        return True

    async def create_payment_intent(
        self,
        session: AsyncSession,
        user_id: int,
        tier: SubscriptionTier,
    ) -> Payment:
        """Create a payment record."""
        config = TierConfig.get_tier_config(tier)
        
        payment = Payment(
            user_id=user_id,
            telegram_payment_id=f"temp_{user_id}_{datetime.utcnow().timestamp()}",
            tier=tier.value,
            amount_in_stars=config["price_in_stars"],
            status="pending",
            currency="XTR",
        )
        session.add(payment)
        await session.flush()
        return payment

    async def process_successful_payment(
        self,
        session: AsyncSession,
        user_id: int,
        telegram_payment_id: str,
        tier: SubscriptionTier,
    ) -> Subscription:
        """Process a successful payment and create/upgrade subscription."""
        config = TierConfig.get_tier_config(tier)
        
        # Update or create subscription
        subscription = await self.get_subscription(session, user_id)
        
        if not subscription:
            subscription = Subscription(
                user_id=user_id,
                tier=tier.value,
                price_in_stars=config["price_in_stars"],
                summaries_per_month=config["summaries_per_month"],
                auto_renew=True,
            )
            subscription.reset_monthly_limit()
        else:
            # Upgrade existing subscription
            subscription.tier = tier.value
            subscription.price_in_stars = config["price_in_stars"]
            subscription.summaries_per_month = config["summaries_per_month"]
            subscription.updated_at = datetime.utcnow()
            subscription.reset_monthly_limit()
        
        # Set expiration (e.g., 30 days from now)
        subscription.expires_at = datetime.utcnow() + timedelta(days=30)
        
        session.add(subscription)
        await session.flush()

        # Create payment record
        stmt = select(Payment).where(Payment.telegram_payment_id == telegram_payment_id)
        result = await session.execute(stmt)
        payment = result.scalar_one_or_none()
        
        if payment:
            payment.mark_completed()
            payment.subscription_id = subscription.id
        else:
            # Payment record not created yet
            payment = Payment(
                user_id=user_id,
                telegram_payment_id=telegram_payment_id,
                tier=tier.value,
                amount_in_stars=config["price_in_stars"],
                status="completed",
                subscription_id=subscription.id,
                currency="XTR",
            )
            payment.mark_completed()
            session.add(payment)

        await session.flush()
        logger.info(f"User {user_id} upgraded to {tier.value} tier")
        
        return subscription

    async def get_user_stats(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> Dict[str, Any]:
        """Get user's subscription stats."""
        subscription = await self.get_subscription(session, user_id)
        
        if not subscription:
            subscription = await self.get_or_create_subscription(session, user_id)

        # Get payment history
        stmt = select(Payment).where(Payment.user_id == user_id).order_by(Payment.created_at.desc())
        result = await session.execute(stmt)
        payments = result.scalars().all()

        return {
            "user_id": user_id,
            "tier": subscription.tier,
            "is_active": subscription.is_active(),
            "summaries_used": subscription.summaries_used_this_month,
            "summaries_limit": subscription.summaries_per_month,
            "days_until_expiry": subscription.days_until_expiry(),
            "expires_at": subscription.expires_at,
            "auto_renew": subscription.auto_renew,
            "total_payments": len(payments),
            "last_payment": payments[0] if payments else None,
        }

    def get_tier_features(self, tier: SubscriptionTier) -> str:
        """Get formatted tier features."""
        config = TierConfig.get_tier_config(tier)
        features_text = "\n".join([f"  • {feature}" for feature in config["features"]])
        return (
            f"<b>{config['name']}</b> - {config['price_in_stars']} ⭐\n"
            f"{config['description']}\n\n"
            f"<b>Features:</b>\n{features_text}"
        )

    def get_all_tiers_display(self) -> str:
        """Get formatted display of all tiers."""
        tiers_text = []
        for tier in [SubscriptionTier.FREE, SubscriptionTier.PRO, SubscriptionTier.ENTERPRISE]:
            config = TierConfig.get_tier_config(tier)
            price_display = "Free" if config["price_in_stars"] == 0 else f"{config['price_in_stars']} ⭐"
            tiers_text.append(
                f"<b>{config['name']}</b> ({price_display})\n"
                f"  {config['summaries_per_month']} summaries/month\n"
            )
        return "\n".join(tiers_text)


# Singleton instance
payment_service = PaymentService()
