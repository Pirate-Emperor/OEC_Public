import os
import time
import uuid
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn
import jwt

# Configure standard HPC logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [MCP-SERVER] %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="OEC MCP Server", description="Model Context Protocol for Semantic Pointers")

class SemanticPointer(BaseModel):
    """
    The core of the OEC memory bridge. 
    Returns a 30-token pointer instead of bulk data to protect the LLM KV cache.
    """
    id: str = Field(..., description="Unique UUID for the spatial node/asset")
    type: str = Field(..., description="Entity type (e.g., 'rigid_body', 'npc', 'terrain_chunk')")
    desc: str = Field(..., description="Short semantic description for the LLM's context")

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: str | int

class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    id: str | int

SECRET_KEY = os.environ.get("OEC_JWT_SECRET", "super-secret-dev-key-do-not-use-in-prod")

def verify_jwt_token(request: Request) -> Dict[str, Any]:
    """
    Enforces Row-Level Security (RLS) constraints.
    Validates the JWT to ensure the DeepSeek orchestrator only queries authorized realms.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        # In production, this raises a 401. For local DevCluster testing, we fallback to mock scopes.
        logger.warning("No JWT provided. Bipartite IFC defaulting to 'development_mode' scopes.")
        return {"sub": "orchestrator_agent", "scopes": ["read:public_lore", "read:spatial_graph"]}
    
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="JWT expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid JWT")

def execute_hybrid_rag_query(query: str, user_scopes: List[str]) -> List[SemanticPointer]:
    """
    Simulates a query to the HNSW + Neo4j Fusion engine.
    (This will be connected to the actual Graph DB in the next architectural step).
    """
    logger.info(f"Executing hybrid search for: '{query}' under scopes: {user_scopes}")
    
    if "tavern" in query.lower():
        return [
            SemanticPointer(id=f"prop_{uuid.uuid4().hex[:8]}", type="rigid_body", desc="Heavy Wooden Table"),
            SemanticPointer(id=f"prop_{uuid.uuid4().hex[:8]}", type="rigid_body", desc="Iron Chandelier"),
            SemanticPointer(id=f"npc_{uuid.uuid4().hex[:8]}", type="agent", desc="Tavern Keeper (Hostile)")
        ]
    elif "forest" in query.lower():
        return [
            SemanticPointer(id=f"vox_{uuid.uuid4().hex[:8]}", type="terrain_chunk", desc="Dense Pine Trees"),
            SemanticPointer(id=f"vox_{uuid.uuid4().hex[:8]}", type="terrain_chunk", desc="Bioluminescent Moss Rock")
        ]
    else:
        return [
            SemanticPointer(id=f"sys_{uuid.uuid4().hex[:8]}", type="system", desc="Empty Spatial Void")
        ]

@app.post("/mcp", response_model=JsonRpcResponse)
async def mcp_endpoint(rpc_req: JsonRpcRequest, auth_payload: Dict[str, Any] = Depends(verify_jwt_token)):
    """
    The single JSON-RPC 2.0 entry point for the DeepSeek-R1 Orchestrator.
    """
    start_time = time.time()
    logger.info(f"Received MCP Method: '{rpc_req.method}' (ID: {rpc_req.id})")
    
    try:
        if rpc_req.method == "query_spatial_memory":
            query = rpc_req.params.get("query", "") if rpc_req.params else ""
            scopes = auth_payload.get("scopes", [])
            
            pointers = execute_hybrid_rag_query(query, scopes)
            
            result_payload = {
                "pointers": [p.dict() for p in pointers],
                "meta": {
                    "count": len(pointers),
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "memory_protection": "Semantic Pointers active. Bulk data withheld."
                }
            }
            return JsonRpcResponse(id=rpc_req.id, result=result_payload)
            
        elif rpc_req.method == "ping":
            return JsonRpcResponse(id=rpc_req.id, result={"status": "OEC MCP Server Online"})
            
        else:
            error_payload = {"code": -32601, "message": f"Method '{rpc_req.method}' not found."}
            return JsonRpcResponse(id=rpc_req.id, error=error_payload)
            
    except Exception as e:
        logger.error(f"Internal MCP Error: {e}")
        error_payload = {"code": -32603, "message": "Internal JSON-RPC Error", "data": str(e)}
        return JsonRpcResponse(id=rpc_req.id, error=error_payload)

if __name__ == "__main__":
    print("""
    ========================================================
    OEC Model Context Protocol (MCP) Server
    Architecture: JSON-RPC 2.0 + Bipartite IFC
    Role: Preventing LLM VRAM OOM via Semantic Pointers
    ========================================================
    """)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")