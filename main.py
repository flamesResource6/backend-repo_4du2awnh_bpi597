import os
import random
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import db, create_document, get_documents

app = FastAPI(title="Crypto Foxes API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Models ----------
class SpinRequest(BaseModel):
    wallet: str = Field(..., description="Wallet address")
    count: int = Field(1, ge=1, le=10, description="Number of spins")
    bundle: Optional[str] = Field(None, description="Bundle name (optional)")


class FoxOut(BaseModel):
    token_id: int
    name: str
    image_url: str
    rarity: str
    attributes: Optional[dict] = None


class BundleOut(BaseModel):
    name: str
    description: Optional[str]
    price_eth: float
    spins: int
    bonus_chance: float
    badge: Optional[str] = None


# ---------- Helpers ----------
RARITY_POOL = [
    ("Common", 0.75),
    ("Rare", 0.18),
    ("Epic", 0.06),
    ("Legendary", 0.01),
]

DEFAULT_BUNDLES: List[BundleOut] = [
    BundleOut(name="Starter Spin", description="One spin to try your luck.", price_eth=0.02, spins=1, bonus_chance=0.0),
    BundleOut(name="Triple Play", description="Three spins + slight bonus chance.", price_eth=0.055, spins=3, bonus_chance=0.02, badge="POPULAR"),
    BundleOut(name="Fox Frenzy", description="Ten spins with boosted epic/legendary odds.", price_eth=0.17, spins=10, bonus_chance=0.05, badge="BEST VALUE"),
]


def weighted_rarity(bonus: float = 0.0) -> str:
    # Apply simple bonus by shifting probability from Common to higher tiers
    adjusted = []
    remaining_common = RARITY_POOL[0][1] - bonus
    remaining_common = max(0.5, remaining_common)
    bonus_pool = RARITY_POOL[0][1] - remaining_common
    # distribute bonus_pool across Rare/Epic/Legendary proportionally
    rare = RARITY_POOL[1][1] + bonus_pool * 0.55
    epic = RARITY_POOL[2][1] + bonus_pool * 0.3
    legendary = RARITY_POOL[3][1] + bonus_pool * 0.15
    adjusted = [("Common", remaining_common), ("Rare", rare), ("Epic", epic), ("Legendary", legendary)]
    r = random.random()
    cum = 0.0
    for name, p in adjusted:
        cum += p
        if r <= cum:
            return name
    return "Common"


def svg_placeholder(token_id: int, rarity: str) -> str:
    palette = {
        "Common": "#6ee7b7",
        "Rare": "#60a5fa",
        "Epic": "#f472b6",
        "Legendary": "#f59e0b",
    }
    color = palette.get(rarity, "#60a5fa")
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='512' height='512' viewBox='0 0 64 64'>
      <rect width='64' height='64' fill='#1f1b2e'/>
      <rect x='8' y='8' width='48' height='48' fill='{color}' opacity='0.2'/>
      <text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' font-family='monospace' font-size='8' fill='{color}'># {token_id}</text>
      <text x='50%' y='58%' dominant-baseline='middle' text-anchor='middle' font-family='monospace' font-size='6' fill='{color}'>{rarity}</text>
    </svg>
    """
    return "data:image/svg+xml;utf8," + svg.replace("\n", "")


# ---------- Routes ----------
@app.get("/")
def read_root():
    return {"name": "Crypto Foxes API", "status": "ok"}


@app.get("/api/bundles", response_model=List[BundleOut])
def get_bundles():
    try:
        docs = get_documents("bundle")
        if not docs:
            return DEFAULT_BUNDLES
        # Map db docs to BundleOut
        resp = []
        for d in docs:
            resp.append(BundleOut(
                name=d.get("name"),
                description=d.get("description"),
                price_eth=float(d.get("price_eth", 0)),
                spins=int(d.get("spins", 1)),
                bonus_chance=float(d.get("bonus_chance", 0.0)),
                badge=d.get("badge")
            ))
        return resp
    except Exception:
        # If db unavailable, still return defaults
        return DEFAULT_BUNDLES


@app.get("/api/last-foxes", response_model=List[FoxOut])
def last_foxes(limit: int = 8):
    try:
        docs = list(db["fox"].find({}).sort("created_at", -1).limit(limit)) if db else []
    except Exception:
        docs = []

    foxes: List[FoxOut] = []
    if docs:
        for d in docs:
            foxes.append(FoxOut(
                token_id=int(d.get("token_id", 0)),
                name=d.get("name", f"Fox #{d.get('token_id', 0)}"),
                image_url=d.get("image_url") or svg_placeholder(int(d.get("token_id", 0)), d.get("rarity", "Common")),
                rarity=d.get("rarity", "Common"),
                attributes=d.get("attributes", {}),
            ))
        return foxes

    # Fallback placeholders
    for i in range(limit):
        tid = 6000 + i
        rarity = random.choices([r[0] for r in RARITY_POOL], weights=[r[1] for r in RARITY_POOL])[0]
        foxes.append(FoxOut(
            token_id=tid,
            name=f"Fox #{tid}",
            image_url=svg_placeholder(tid, rarity),
            rarity=rarity,
            attributes={"Background": "Neon", "Eyes": "Bright"}
        ))
    return foxes


@app.post("/api/spin", response_model=List[FoxOut])
def spin(req: SpinRequest):
    if not req.wallet:
        raise HTTPException(status_code=400, detail="wallet required")

    # bundle bonus
    bonus = 0.0
    if req.bundle:
        try:
            b = db["bundle"].find_one({"name": req.bundle}) if db else None
            if b:
                bonus = float(b.get("bonus_chance", 0.0))
            else:
                # match default bundles
                for d in DEFAULT_BUNDLES:
                    if d.name == req.bundle:
                        bonus = d.bonus_chance
                        break
        except Exception:
            for d in DEFAULT_BUNDLES:
                if d.name == req.bundle:
                    bonus = d.bonus_chance
                    break

    minted: List[FoxOut] = []
    for i in range(req.count):
        rarity = weighted_rarity(bonus)
        token_id = int(datetime.utcnow().timestamp()) % 100000 + random.randint(1, 999)
        name = f"Fox #{token_id}"
        img = svg_placeholder(token_id, rarity)
        doc_id = None
        try:
            # Persist fox
            doc_id = create_document("fox", {
                "token_id": token_id,
                "name": name,
                "image_url": img,
                "rarity": rarity,
                "attributes": {"Fur": "Pixel", "Eyes": "Neon"},
            })
            # Persist transaction
            create_document("minttransaction", {
                "wallet": req.wallet,
                "token_id": token_id,
                "cost_eth": 0.02,  # placeholder
            })
        except Exception:
            pass
        minted.append(FoxOut(token_id=token_id, name=name, image_url=img, rarity=rarity, attributes={"Fur": "Pixel", "Eyes": "Neon"}))
    return minted


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
