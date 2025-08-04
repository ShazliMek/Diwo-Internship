#!/usr/bin/env python3
"""
Sample MCP Server
Simple example server for testing
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/sample_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SampleMCPServer')

# Configuration
CONFIG_FILE = "config/sample_server.json"

def load_config():
    """Load server configuration"""
    logger.info("Loading server configuration...")
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            logger.info(f"Configuration loaded successfully: {config}")
            return config
    except FileNotFoundError:
        logger.warning(f"Config file {CONFIG_FILE} not found, using defaults")
        default_config = {
            "server": {
                "name": "Sample MCP Server",
                "transport": "stdio",
                "port": 8001
            }
        }
        logger.info(f"Using default configuration: {default_config}")
        return default_config

# Load configuration
config = load_config()
logger.info(f"Sample MCP Server initializing with config: {config['server']['name']}")

# Server instance
server = Server("SampleServer")
logger.info("Server instance created")

@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available tools"""
    logger.info("Received list_tools request")
    tools = [
        Tool(
            name="echo",
            description="Echo back the input message",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to echo"}
                },
                "required": ["message"]
            }
        )
    ]
    logger.info(f"Returning {len(tools)} tools: {[tool.name for tool in tools]}")
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> List[TextContent]:
    """Handle tool execution"""
    logger.info(f"Received call_tool request - Tool: {name}, Arguments: {arguments}")
    
    if name == "echo":
        message = arguments.get('message', '')
        response_text = f"Echo: {message}"
        logger.info(f"Echo tool executed successfully - Input: '{message}', Output: '{response_text}'")
        return [TextContent(
            type="text",
            text=response_text
        )]
    else:
        error_msg = f"Unknown tool: {name}"
        logger.error(f"Tool execution failed - {error_msg}")
        return [TextContent(
            type="text",
            text=f"❌ {error_msg}"
        )]

if __name__ == "__main__":
    import argparse
    
    # Create logs directory if it doesn't exist
    import os
    os.makedirs('logs', exist_ok=True)
    
    parser = argparse.ArgumentParser(description="Sample MCP Server")
    parser.add_argument("--transport", choices=["stdio"], default="stdio")
    
    args = parser.parse_args()
    logger.info(f"Starting Sample MCP Server with transport: {args.transport}")
    
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
