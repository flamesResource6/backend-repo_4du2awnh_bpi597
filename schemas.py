"""
Database Schemas for Crypto Foxes

Each Pydantic model maps to a MongoDB collection (lowercased class name).
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class Fox(BaseModel):
    """
    Collection: "fox"
    Represents a minted Crypto Fox NFT
    """
    token_id: int = Field(..., ge=0, description="Unique token id")
    name: str = Field(..., description="Display name of the fox")
    image_url: str = Field(..., description="Public image URL for the fox artwork")
    rarity: str = Field(..., description="Rarity tier: Common, Rare, Epic, Legendary")
    attributes: Optional[Dict[str, str]] = Field(default_factory=dict, description="Trait map")


class Bundle(BaseModel):
    """
    Collection: "bundle"
    Special bundle offers for spins
    """
    name: str
    description: Optional[str] = None
    price_eth: float = Field(..., ge=0)
    spins: int = Field(..., ge=1, description="Number of spins included")
    bonus_chance: float = Field(0.0, ge=0, le=1, description="Extra chance for higher rarity")
    badge: Optional[str] = Field(None, description="UI badge e.g., BEST VALUE")


class MintTransaction(BaseModel):
    """
    Collection: "minttransaction"
    Records a mint action
    """
    wallet: str = Field(..., description="Wallet address or identifier")
    token_id: int
    cost_eth: float = Field(..., ge=0)
