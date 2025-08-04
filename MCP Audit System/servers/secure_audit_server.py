#!/usr/bin/env python3
"""
SecureAudit MCP Server
Main audit management server with full CRUD operations
"""

import asyncio
import logging
import json
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager
import threading
from queue import Queue

# FastMCP v2 imports
from mcp import ClientSession, StdioServerParameters
from mcp.server import Server

# Configure comprehensive logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/secure_audit_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SecureAuditMCPServer')
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest, CallToolResult, 
    GetPromptRequest, GetPromptResult,
    ListPromptsRequest, ListPromptsResult,
    ListResourcesRequest, ListResourcesResult,
    ListToolsRequest, ListToolsResult,
    ReadResourceRequest, ReadResourceResult,
    Resource, Tool, Prompt, TextContent, ImageContent, EmbeddedResource
)

# Configuration
CONFIG_FILE = "config/secure_audit_server.json"

def load_config():
    """Load server configuration"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"Config file {CONFIG_FILE} not found, using defaults")
        return {
            "server": {
                "name": "SecureAudit MCP Server",
                "transport": "stdio",
                "port": 8000,
                "host": "127.0.0.1"
            },
            "database": {
                "path": "audit_database.db"
            },
            "logging": {
                "level": "INFO"
            }
        }

# Load configuration
config = load_config()

# Database Manager
class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection_pool = Queue(maxsize=10)
        self._init_database()
        self._populate_pool()
    
    def _init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'open',
                assigned_auditor TEXT,
                created_date TEXT,
                due_date TEXT,
                priority TEXT DEFAULT 'medium',
                department TEXT,
                notes TEXT,
                attachments TEXT,
                last_updated TEXT
            )
        ''')
        conn.commit()
        conn.close()
    
    def _populate_pool(self):
        """Populate connection pool"""
        for _ in range(10):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self.connection_pool.put(conn)
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool"""
        conn = self.connection_pool.get()
        try:
            yield conn
        finally:
            self.connection_pool.put(conn)

# Initialize database
db = DatabaseManager(config.get("database", {}).get("path", "audit_database.db"))

# Server instance
server = Server("SecureAudit")
logger.info("SecureAudit MCP Server instance created")

@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available audit management tools"""
    logger.info("Received list_tools request")
    tools = [
        Tool(
            name="create_audit",
            description="Create a new audit record",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Audit title"},
                    "description": {"type": "string", "description": "Audit description"},
                    "assigned_auditor": {"type": "string", "description": "Assigned auditor name"},
                    "due_date": {"type": "string", "description": "Due date (YYYY-MM-DD)"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
                    "department": {"type": "string", "description": "Department being audited"}
                },
                "required": ["title", "assigned_auditor"]
            }
        ),
        Tool(
            name="get_audit",
            description="Get audit details by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "audit_id": {"type": "integer", "description": "Audit ID"}
                },
                "required": ["audit_id"]
            }
        ),
        Tool(
            name="list_audits",
            description="List audits with optional filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status"},
                    "assigned_auditor": {"type": "string", "description": "Filter by auditor"},
                    "department": {"type": "string", "description": "Filter by department"},
                    "limit": {"type": "integer", "default": 50, "description": "Maximum results"}
                }
            }
        ),
        Tool(
            name="update_audit",
            description="Update an existing audit",
            inputSchema={
                "type": "object",
                "properties": {
                    "audit_id": {"type": "integer", "description": "Audit ID"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string", "enum": ["open", "in_progress", "completed", "closed", "cancelled"]},
                    "assigned_auditor": {"type": "string"},
                    "due_date": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                    "department": {"type": "string"},
                    "notes": {"type": "string"}
                },
                "required": ["audit_id"]
            }
        ),
        Tool(
            name="delete_audit",
            description="Delete an audit record",
            inputSchema={
                "type": "object",
                "properties": {
                    "audit_id": {"type": "integer", "description": "Audit ID"}
                },
                "required": ["audit_id"]
            }
        ),
        Tool(
            name="get_audit_statistics",
            description="Get audit statistics and metrics",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["week", "month", "quarter", "year"], "default": "month"}
                }
            }
        )
    ]
    logger.info(f"Returning {len(tools)} tools")
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> List[TextContent]:
    """Handle tool execution"""
    logger.info(f"Received call_tool request - Tool: {name}, Arguments: {arguments}")
    start_time = datetime.now()
    
    if name == "create_audit":
        logger.info(f"Creating new audit: {arguments.get('title', 'Unknown Title')}")
        try:
            async with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO audits (title, description, assigned_auditor, due_date, priority, department, created_date, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    arguments["title"],
                    arguments.get("description", ""),
                    arguments["assigned_auditor"],
                    arguments.get("due_date"),
                    arguments.get("priority", "medium"),
                    arguments.get("department"),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                audit_id = cursor.lastrowid
                conn.commit()
                
                execution_time = (datetime.now() - start_time).total_seconds()
                logger.info(f"Audit created successfully - ID: {audit_id} (execution time: {execution_time:.3f}s)")
                
                return [TextContent(
                    type="text",
                    text=f"✅ Created audit #{audit_id}: {arguments['title']}"
                )]
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Failed to create audit: {e} (execution time: {execution_time:.3f}s)")
            return [TextContent(
                type="text",
                text=f"❌ Error creating audit: {str(e)}"
            )]
    
    elif name == "get_audit":
        async with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM audits WHERE id = ?', (arguments["audit_id"],))
            audit = cursor.fetchone()
            
            if audit:
                audit_dict = dict(audit)
                return [TextContent(
                    type="text",
                    text=json.dumps(audit_dict, indent=2)
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"❌ Audit #{arguments['audit_id']} not found"
                )]
    
    elif name == "list_audits":
        async with db.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM audits WHERE 1=1"
            params = []
            
            if arguments.get("status"):
                query += " AND status = ?"
                params.append(arguments["status"])
            
            if arguments.get("assigned_auditor"):
                query += " AND assigned_auditor = ?"
                params.append(arguments["assigned_auditor"])
            
            if arguments.get("department"):
                query += " AND department = ?"
                params.append(arguments["department"])
            
            query += f" ORDER BY created_date DESC LIMIT {arguments.get('limit', 50)}"
            
            cursor.execute(query, params)
            audits = cursor.fetchall()
            
            audit_list = [dict(audit) for audit in audits]
            return [TextContent(
                type="text",
                text=json.dumps(audit_list, indent=2)
            )]
    
    elif name == "update_audit":
        async with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build dynamic update query
            set_clauses = []
            params = []
            
            for field in ["title", "description", "status", "assigned_auditor", "due_date", "priority", "department", "notes"]:
                if field in arguments:
                    set_clauses.append(f"{field} = ?")
                    params.append(arguments[field])
            
            if set_clauses:
                set_clauses.append("last_updated = ?")
                params.append(datetime.now().isoformat())
                params.append(arguments["audit_id"])
                
                query = f"UPDATE audits SET {', '.join(set_clauses)} WHERE id = ?"
                cursor.execute(query, params)
                conn.commit()
                
                if cursor.rowcount > 0:
                    return [TextContent(
                        type="text",
                        text=f"✅ Updated audit #{arguments['audit_id']}"
                    )]
                else:
                    return [TextContent(
                        type="text",
                        text=f"❌ Audit #{arguments['audit_id']} not found"
                    )]
            else:
                return [TextContent(
                    type="text",
                    text="❌ No fields to update"
                )]
    
    elif name == "delete_audit":
        async with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM audits WHERE id = ?', (arguments["audit_id"],))
            conn.commit()
            
            if cursor.rowcount > 0:
                return [TextContent(
                    type="text",
                    text=f"✅ Deleted audit #{arguments['audit_id']}"
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"❌ Audit #{arguments['audit_id']} not found"
                )]
    
    elif name == "get_audit_statistics":
        async with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Calculate date range based on period
            now = datetime.now()
            if arguments.get("period") == "week":
                start_date = now - timedelta(weeks=1)
            elif arguments.get("period") == "quarter":
                start_date = now - timedelta(days=90)
            elif arguments.get("period") == "year":
                start_date = now - timedelta(days=365)
            else:  # month
                start_date = now - timedelta(days=30)
            
            # Get statistics
            cursor.execute('SELECT COUNT(*) as total FROM audits')
            total = cursor.fetchone()[0]
            
            cursor.execute('SELECT status, COUNT(*) as count FROM audits GROUP BY status')
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            cursor.execute('SELECT assigned_auditor, COUNT(*) as count FROM audits GROUP BY assigned_auditor')
            auditor_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            stats = {
                "total_audits": total,
                "status_breakdown": status_counts,
                "auditor_workload": auditor_counts,
                "period": arguments.get("period", "month")
            }
            
            return [TextContent(
                type="text",
                text=json.dumps(stats, indent=2)
            )]
    
    else:
        error_msg = f"Unknown tool: {name}"
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"Tool execution failed - {error_msg} (execution time: {execution_time:.3f}s)")
        return [TextContent(
            type="text",
            text=f"❌ {error_msg}"
        )]

if __name__ == "__main__":
    import argparse
    
    # Create logs directory if it doesn't exist
    import os
    os.makedirs('logs', exist_ok=True)
    
    parser = argparse.ArgumentParser(description="SecureAudit MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    
    args = parser.parse_args()
    logger.info(f"Starting SecureAudit MCP Server with transport: {args.transport}")
    
    if args.transport == "stdio":
        async def main():
            logger.info("Initializing stdio server...")
            try:
                async with stdio_server() as (read_stream, write_stream):
                    logger.info("stdio server initialized successfully, starting server...")
                    await server.run(read_stream, write_stream, {})
            except Exception as e:
                logger.error(f"Server error: {e}")
                raise
        
        logger.info("Starting asyncio event loop...")
        asyncio.run(main())
    else:
        logger.warning(f"Transport {args.transport} not implemented yet")
        print(f"Transport {args.transport} not implemented yet")
