#!/usr/bin/env python3
"""
Sample MCP Server
Simple example server for testing MCP functionality
"""

import asyncio
import json
import logging
import argparse
import sys
from datetime import datetime
from typing import Dict, Any

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('SampleMCPServer')

class SimpleMCPServer:
    """Simple MCP server implementation for testing"""
    
    def __init__(self):
        self.tools = {
            'echo': self.echo_tool
        }
        logger.info("Sample MCP Server initialized")
    
    async def echo_tool(self, message: str = "Hello, World!") -> Dict[str, Any]:
        """
        Simple echo tool that returns the input message
        
        Args:
            message: Message to echo back
        
        Returns:
            Dictionary with the echoed message and timestamp
        """
        logger.info(f"Echo tool called with message: {message}")
        
        return {
            'success': True,
            'echoed_message': message,
            'timestamp': datetime.now().isoformat(),
            'server': 'Sample MCP Server'
        }
    
    async def handle_tool_call(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Handle tool calls"""
        if tool_name in self.tools:
            try:
                result = await self.tools[tool_name](**kwargs)
                logger.info(f"Tool '{tool_name}' executed successfully")
                return result
            except Exception as e:
                logger.error(f"Tool '{tool_name}' failed: {str(e)}")
                return {
                    'success': False,
                    'error': str(e),
                    'tool': tool_name
                }
        else:
            logger.warning(f"Unknown tool requested: {tool_name}")
            return {
                'success': False,
                'error': f'Unknown tool: {tool_name}',
                'available_tools': list(self.tools.keys())
            }
    
    async def get_capabilities(self) -> Dict[str, Any]:
        """Get server capabilities"""
        return {
            'tools': [
                {
                    'name': 'echo',
                    'description': 'Echo back a message with timestamp',
                    'parameters': {
                        'message': {
                            'type': 'string',
                            'description': 'Message to echo back',
                            'default': 'Hello, World!'
                        }
                    }
                }
            ],
            'resources': [],
            'prompts': [],
            'server_info': {
                'name': 'Sample MCP Server',
                'version': '1.0.0',
                'description': 'Simple example server for testing MCP functionality'
            }
        }
    
    def run_stdio(self):
        """Run server with stdio transport (simplified)"""
        logger.info("Running Sample MCP Server with stdio transport")
        
        # Simplified stdio loop for testing
        try:
            while True:
                try:
                    # Read input
                    line = input()
                    if not line:
                        continue
                    
                    # Parse JSON-RPC request
                    try:
                        request = json.loads(line)
                    except json.JSONDecodeError:
                        print(json.dumps({
                            'error': 'Invalid JSON',
                            'timestamp': datetime.now().isoformat()
                        }))
                        continue
                    
                    # Handle request
                    if request.get('method') == 'tools/call':
                        tool_name = request.get('params', {}).get('name', '')
                        tool_args = request.get('params', {}).get('arguments', {})
                        
                        # Call tool
                        result = asyncio.run(self.handle_tool_call(tool_name, **tool_args))
                        
                        # Send response
                        response = {
                            'id': request.get('id'),
                            'result': result
                        }
                        print(json.dumps(response))
                    
                    elif request.get('method') == 'initialize':
                        capabilities = asyncio.run(self.get_capabilities())
                        response = {
                            'id': request.get('id'),
                            'result': capabilities
                        }
                        print(json.dumps(response))
                    
                    else:
                        response = {
                            'id': request.get('id'),
                            'error': f'Unknown method: {request.get("method")}'
                        }
                        print(json.dumps(response))
                
                except EOFError:
                    break
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Error handling request: {str(e)}")
                    print(json.dumps({
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    }))
        
        except KeyboardInterrupt:
            logger.info("Server shutting down...")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Sample MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport method to use"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port to bind to"
    )
    
    args = parser.parse_args()
    
    server = SimpleMCPServer()
    
    logger.info(f"Starting Sample MCP Server with transport: {args.transport}")
    
    if args.transport == "stdio":
        server.run_stdio()
    else:
        logger.error(f"Transport {args.transport} not implemented in sample server")
        sys.exit(1)

if __name__ == "__main__":
    main()
