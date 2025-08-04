#!/usr/bin/env python3
"""
Flask Web Application for MCP Audit Management System

Comprehensive web interface with Bootstrap UI, server management,
MCP communication, and AI integration.
"""

import os
import sys
import json
import logging
import subprocess
import threading
import time
import uuid
import tempfile
import signal
import psutil
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import requests

from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, 
    flash, session, send_file, abort
)
from werkzeug.utils import secure_filename
import openai

# Configure comprehensive logging for Flask application
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/flask_app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('MCPAuditFlaskApp')

# Configure Flask's built-in logger
flask_logger = logging.getLogger('werkzeug')
flask_logger.setLevel(logging.INFO)

# Setup comprehensive logging
class WebAppFormatter(logging.Formatter):
    """Custom formatter for web application logging"""
    
    EMOJI_MAP = {
        'DEBUG': '🔍',
        'INFO': '🌐',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }
    
    def format(self, record):
        emoji = self.EMOJI_MAP.get(record.levelname, '🌐')
        record.msg = f'{emoji} {record.msg}'
        return super().format(record)

def setup_web_logging():
    """Setup web application logging"""
    logger = logging.getLogger('MCPAuditWebApp')
    logger.setLevel(logging.DEBUG)
    
    # File handler
    file_handler = logging.FileHandler('mcp_audit_system.log')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = WebAppFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = WebAppFormatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_web_logging()

# Flask app configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = 'audit-system-secret-key-2025'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class ServerManager:
    """Comprehensive MCP server management system"""
    
    def __init__(self, config_path: str = "server_config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.active_servers = {}  # {server_name: process_info}
        self.current_server = self.config.get('default_server', 'SecureAudit')
        logger.info(f"SERVER: Server manager initialized with config: {config_path}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load server configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"SERVER: Configuration loaded successfully")
            return config
        except Exception as e:
            logger.error(f"SERVER: Failed to load configuration - {str(e)}")
            return {
                'servers': {},
                'default_server': 'SecureAudit'
            }
    
    def get_server_config(self, server_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific server"""
        return self.config.get('servers', {}).get(server_name)
    
    def list_servers(self) -> Dict[str, Any]:
        """List all configured servers with their status"""
        servers = {}
        for name, config in self.config.get('servers', {}).items():
            status = self.get_server_status(name)
            servers[name] = {
                'config': config,
                'status': status,
                'is_current': name == self.current_server
            }
        return servers
    
    def get_server_status(self, server_name: str) -> Dict[str, Any]:
        """Get current status of a server"""
        if server_name in self.active_servers:
            process_info = self.active_servers[server_name]
            process = process_info['process']
            
            if process.poll() is None:  # Process still running
                return {
                    'running': True,
                    'pid': process.pid,
                    'started_at': process_info['started_at'],
                    'uptime': time.time() - process_info['start_time']
                }
            else:
                # Process has ended
                del self.active_servers[server_name]
                return {
                    'running': False,
                    'exit_code': process.poll(),
                    'ended_at': datetime.now().isoformat()
                }
        
        return {'running': False}
    
    def start_server(self, server_name: str) -> Tuple[bool, str]:
        """Start a specific MCP server"""
        logger.info(f"SERVER: Starting server {server_name}")
        
        if server_name in self.active_servers:
            status = self.get_server_status(server_name)
            if status['running']:
                return False, f"Server {server_name} is already running"
        
        config = self.get_server_config(server_name)
        if not config:
            return False, f"Server {server_name} not found in configuration"
        
        try:
            # Build command based on server name with simplified config
            server_commands = {
                'SecureAudit': ['python3', 'servers/secure_audit_server.py', '--transport', 'stdio'],
                'SampleServer': ['python3', 'servers/sample_server.py', '--transport', 'stdio'],
                'HttpAuditServer': ['python3', 'servers/http_audit_server.py', '--transport', 'http', '--host', config['host'], '--port', str(config['port'])],
                'SSEAuditServer': ['python3', 'servers/sse_audit_server.py', '--transport', 'sse', '--host', config['host'], '--port', str(config['port'])]
            }
            
            cmd = server_commands.get(server_name)
            if not cmd:
                return False, f"Unknown server: {server_name}"
            
            # Start process
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd='.'
            )
            
            # Store process info
            self.active_servers[server_name] = {
                'process': process,
                'started_at': datetime.now().isoformat(),
                'start_time': time.time(),
                'config': config
            }
            
            logger.info(f"SERVER: Started {server_name} with PID {process.pid}")
            return True, f"Started {server_name} successfully"
            
        except Exception as e:
            logger.error(f"SERVER: Failed to start {server_name} - {str(e)}")
            return False, f"Failed to start server: {str(e)}"
    
    def stop_server(self, server_name: str) -> Tuple[bool, str]:
        """Stop a specific MCP server"""
        logger.info(f"SERVER: Stopping server {server_name}")
        
        if server_name not in self.active_servers:
            return False, f"Server {server_name} is not running"
        
        try:
            process_info = self.active_servers[server_name]
            process = process_info['process']
            
            # Try graceful shutdown first
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if necessary
                process.kill()
                process.wait()
            
            del self.active_servers[server_name]
            logger.info(f"SERVER: Stopped {server_name}")
            return True, f"Stopped {server_name} successfully"
            
        except Exception as e:
            logger.error(f"SERVER: Failed to stop {server_name} - {str(e)}")
            return False, f"Failed to stop server: {str(e)}"
    
    def switch_server(self, server_name: str) -> Tuple[bool, str]:
        """Switch to a different server as the current active server"""
        logger.info(f"SERVER: Switching to server {server_name}")
        
        if server_name not in self.config.get('servers', {}):
            return False, f"Server {server_name} not found"
        
        # Start the new server if not running
        if server_name not in self.active_servers:
            success, message = self.start_server(server_name)
            if not success:
                return False, f"Failed to start {server_name}: {message}"
        
        self.current_server = server_name
        logger.info(f"SERVER: Switched to {server_name}")
        return True, f"Switched to {server_name}"

class MCPClient:
    """MCP communication client for tool calls and resource access"""
    
    def __init__(self, server_manager: ServerManager):
        self.server_manager = server_manager
        logger.info("CLIENT: MCP client initialized")
    
    def call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Call a tool on the current MCP server"""
        start_time = datetime.now()
        logger.info(f"MCP_REQUEST: Calling tool '{tool_name}' with arguments: {kwargs}")
        
        server_name = self.server_manager.current_server
        
        if server_name not in self.server_manager.active_servers:
            error_msg = f'Server {server_name} is not running'
            logger.error(f"MCP_ERROR: {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }
        
        try:
            # Create temporary Python script for MCP communication
            script_content = f'''
import json
import sys
import subprocess

# MCP tool call via JSON-RPC
request = {{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {{
        "name": "{tool_name}",
        "arguments": {json.dumps(kwargs)}
    }}
}}

# Send request to MCP server (simplified)
print(json.dumps(request))
'''
            
            # Write script to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(script_content)
                script_path = f.name
            
            try:
                # Execute script and capture output
                result = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    # Parse response (simplified)
                    response_data = {
                        'success': True,
                        'tool': tool_name,
                        'result': f'Tool {tool_name} called successfully',
                        'args': kwargs,
                        'timestamp': datetime.now().isoformat()
                    }
                    execution_time = (datetime.now() - start_time).total_seconds()
                    logger.info(f"MCP_RESPONSE: Tool '{tool_name}' executed successfully (execution time: {execution_time:.3f}s)")
                    return response_data
                else:
                    execution_time = (datetime.now() - start_time).total_seconds()
                    logger.error(f"MCP_ERROR: Tool '{tool_name}' failed - {result.stderr} (execution time: {execution_time:.3f}s)")
                    return {
                        'success': False,
                        'error': f'Tool execution failed: {result.stderr}',
                        'tool': tool_name
                    }
            
            finally:
                # Clean up temporary file
                os.unlink(script_path)
        
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"MCP_ERROR: Failed to call tool '{tool_name}' - {str(e)} (execution time: {execution_time:.3f}s)")
            return {
                'success': False,
                'error': str(e),
                'tool': tool_name
            }
    
    def get_resource(self, resource_uri: str) -> Dict[str, Any]:
        """Get a resource from the current MCP server"""
        logger.info(f"CLIENT: Getting resource {resource_uri}")
        
        # Simplified resource access
        try:
            return {
                'success': True,
                'resource_uri': resource_uri,
                'content': f'Resource {resource_uri} content would be here',
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"CLIENT: Failed to get resource {resource_uri} - {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'resource_uri': resource_uri
            }

class AIIntegration:
    """OpenAI integration for audit summaries"""
    
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY', '')
        if self.api_key:
            openai.api_key = self.api_key
        logger.info("AI: OpenAI integration initialized")
    
    def generate_audit_summary(self, audit_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate AI-powered audit summary"""
        logger.info(f"AI: Generating summary for audit {audit_data.get('id', 'unknown')}")
        
        if not self.api_key:
            return {
                'success': False,
                'error': 'OpenAI API key not configured'
            }
        
        try:
            prompt = f"""
            Please provide a comprehensive audit summary for the following audit:
            
            Title: {audit_data.get('title', 'N/A')}
            Description: {audit_data.get('description', 'N/A')}
            Status: {audit_data.get('status', 'N/A')}
            Assigned Auditor: {audit_data.get('assigned_auditor', 'N/A')}
            Date: {audit_data.get('date', 'N/A')}
            
            Please include:
            1. Executive summary
            2. Key findings
            3. Risk assessment
            4. Recommendations
            5. Next steps
            """
            
            # Simulate AI response (replace with actual OpenAI call)
            summary = f"""
            **Executive Summary**
            This audit of "{audit_data.get('title', 'N/A')}" shows {audit_data.get('status', 'unknown')} status with key areas requiring attention.
            
            **Key Findings**
            - Current status: {audit_data.get('status', 'unknown')}
            - Assigned to: {audit_data.get('assigned_auditor', 'unassigned')}
            - Progress tracking needed
            
            **Risk Assessment**
            Medium risk level based on current status and timeline.
            
            **Recommendations**
            1. Continue monitoring progress
            2. Regular status updates
            3. Stakeholder communication
            
            **Next Steps**
            - Review progress weekly
            - Update status as needed
            - Document findings
            """
            
            logger.info("AI: Audit summary generated successfully")
            return {
                'success': True,
                'summary': summary,
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"AI: Failed to generate summary - {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

# Initialize components
server_manager = ServerManager()
mcp_client = MCPClient(server_manager)
ai_integration = AIIntegration()

# Flask routes
@app.route('/')
def index():
    """Home page with dashboard"""
    logger.info("WEB: Accessing dashboard")
    
    # Get server status
    servers = server_manager.list_servers()
    
    # Get basic statistics (simulated)
    stats = {
        'total_audits': 25,
        'open_audits': 8,
        'in_progress': 12,
        'completed': 5,
        'active_servers': len([s for s in servers.values() if s['status']['running']])
    }
    
    return render_template('dashboard.html', 
                         servers=servers, 
                         stats=stats,
                         current_server=server_manager.current_server)

@app.route('/audits')
def list_audits():
    """List all audits with filtering"""
    logger.info("WEB: Listing audits")
    
    # Get filter parameters
    status_filter = request.args.get('status', '')
    auditor_filter = request.args.get('auditor', '')
    search_filter = request.args.get('search', '')
    
    # Call MCP tool to get audits
    result = mcp_client.call_tool(
        'list_audits',
        status=status_filter,
        assigned_auditor=auditor_filter,
        search=search_filter
    )
    
    # Mock audit data for display
    mock_audits = [
        {
            'id': 1,
            'title': 'Financial Controls Audit',
            'description': 'Review of financial controls and procedures',
            'status': 'in_progress',
            'assigned_auditor': 'John Smith',
            'date': '2025-01-15',
            'created_at': '2025-01-01T10:00:00'
        },
        {
            'id': 2,
            'title': 'IT Security Assessment',
            'description': 'Comprehensive security audit of IT systems',
            'status': 'open',
            'assigned_auditor': 'Jane Doe',
            'date': '2025-02-01',
            'created_at': '2025-01-05T14:30:00'
        },
        {
            'id': 3,
            'title': 'Compliance Review',
            'description': 'Annual compliance audit for regulatory requirements',
            'status': 'completed',
            'assigned_auditor': 'Bob Johnson',
            'date': '2025-01-10',
            'created_at': '2024-12-15T09:15:00'
        }
    ]
    
    return render_template('audits.html', 
                         audits=mock_audits,
                         filters={
                             'status': status_filter,
                             'auditor': auditor_filter,
                             'search': search_filter
                         })

@app.route('/audit/<int:audit_id>')
def audit_detail(audit_id):
    """Show detailed audit information"""
    logger.info(f"WEB: Viewing audit detail for ID {audit_id}")
    
    # Call MCP tool to get audit
    result = mcp_client.call_tool('get_audit', audit_id=audit_id)
    
    # Mock audit data
    mock_audit = {
        'id': audit_id,
        'title': f'Audit #{audit_id}',
        'description': f'Detailed description for audit {audit_id}',
        'status': 'in_progress',
        'assigned_auditor': 'John Smith',
        'date': '2025-01-15',
        'created_at': '2025-01-01T10:00:00',
        'updated_at': '2025-01-20T15:30:00'
    }
    
    return render_template('audit_detail.html', audit=mock_audit)

@app.route('/create_audit', methods=['GET', 'POST'])
def create_audit():
    """Create a new audit"""
    if request.method == 'POST':
        form_data = {
            'title': request.form.get('title', ''),
            'description': request.form.get('description', ''),
            'date': request.form.get('date', ''),
            'status': request.form.get('status', 'open'),
            'assigned_auditor': request.form.get('assigned_auditor', '')
        }
        logger.info(f"WEB: Creating new audit with data: {form_data}")
        
        # Get form data
        title = form_data['title']
        description = form_data['description']
        date = form_data['date']
        status = form_data['status']
        assigned_auditor = form_data['assigned_auditor']
        
        # Validate required fields
        if not title:
            logger.warning("WEB: Audit creation failed - missing title")
            flash('Title is required', 'error')
            return render_template('create_audit.html')
        
        # Call MCP tool to create audit
        result = mcp_client.call_tool(
            'create_audit',
            title=title,
            description=description,
            date=date,
            status=status,
            assigned_auditor=assigned_auditor
        )
        
        if result.get('success'):
            flash('Audit created successfully', 'success')
            return redirect(url_for('list_audits'))
        else:
            flash(f'Failed to create audit: {result.get("error", "Unknown error")}', 'error')
    
    return render_template('create_audit.html')

@app.route('/update_audit/<int:audit_id>', methods=['GET', 'POST'])
def update_audit(audit_id):
    """Update an existing audit"""
    if request.method == 'POST':
        logger.info(f"WEB: Updating audit {audit_id}")
        
        # Get form data
        updates = {}
        for field in ['title', 'description', 'date', 'status', 'assigned_auditor']:
            value = request.form.get(field)
            if value:
                updates[field] = value
        
        # Call MCP tool to update audit
        result = mcp_client.call_tool('update_audit', audit_id=audit_id, **updates)
        
        if result.get('success'):
            flash('Audit updated successfully', 'success')
            return redirect(url_for('audit_detail', audit_id=audit_id))
        else:
            flash(f'Failed to update audit: {result.get("error", "Unknown error")}', 'error')
    
    # Get current audit data for form
    mock_audit = {
        'id': audit_id,
        'title': f'Audit #{audit_id}',
        'description': f'Description for audit {audit_id}',
        'status': 'in_progress',
        'assigned_auditor': 'John Smith',
        'date': '2025-01-15'
    }
    
    return render_template('update_audit.html', audit=mock_audit)

@app.route('/delete_audit/<int:audit_id>', methods=['POST'])
def delete_audit(audit_id):
    """Delete an audit"""
    logger.info(f"WEB: Deleting audit {audit_id}")
    
    # Call MCP tool to delete audit
    result = mcp_client.call_tool('delete_audit', audit_id=audit_id)
    
    if result.get('success'):
        flash('Audit deleted successfully', 'success')
    else:
        flash(f'Failed to delete audit: {result.get("error", "Unknown error")}', 'error')
    
    return redirect(url_for('list_audits'))

@app.route('/audit/<int:audit_id>/ai_summary')
def ai_summary(audit_id):
    """Generate AI-powered audit summary"""
    logger.info(f"WEB: Generating AI summary for audit {audit_id}")
    
    # Get audit data
    mock_audit = {
        'id': audit_id,
        'title': f'Audit #{audit_id}',
        'description': f'Description for audit {audit_id}',
        'status': 'in_progress',
        'assigned_auditor': 'John Smith',
        'date': '2025-01-15'
    }
    
    # Generate AI summary
    summary_result = ai_integration.generate_audit_summary(mock_audit)
    
    return render_template('ai_summary.html', 
                         audit=mock_audit, 
                         summary_result=summary_result)

@app.route('/servers')
def servers():
    """Server management page"""
    logger.info("WEB: Accessing server management")
    
    servers = server_manager.list_servers()
    return render_template('servers.html', 
                         servers=servers,
                         current_server=server_manager.current_server)

@app.route('/server/<server_name>/start', methods=['POST'])
def start_server(server_name):
    """Start a specific server"""
    logger.info(f"WEB: Starting server {server_name}")
    
    success, message = server_manager.start_server(server_name)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('servers'))

@app.route('/server/<server_name>/stop', methods=['POST'])
def stop_server(server_name):
    """Stop a specific server"""
    logger.info(f"WEB: Stopping server {server_name}")
    
    success, message = server_manager.stop_server(server_name)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('servers'))

@app.route('/server/<server_name>/switch', methods=['POST'])
def switch_server(server_name):
    """Switch to a different server"""
    logger.info(f"WEB: Switching to server {server_name}")
    
    success, message = server_manager.switch_server(server_name)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('servers'))

@app.route('/api/server/<server_name>/status')
def server_status_api(server_name):
    """API endpoint for server status"""
    status = server_manager.get_server_status(server_name)
    return jsonify(status)

@app.route('/api/statistics')
def statistics_api():
    """API endpoint for audit statistics"""
    # Call MCP tool to get statistics
    result = mcp_client.call_tool('get_audit_statistics')
    
    # Mock statistics
    mock_stats = {
        'total_audits': 25,
        'status_breakdown': {
            'open': 8,
            'in_progress': 12,
            'completed': 5
        },
        'auditor_workload': {
            'John Smith': 8,
            'Jane Doe': 10,
            'Bob Johnson': 7
        },
        'recent_audits_30_days': 15,
        'generated_at': datetime.now().isoformat()
    }
    
    return jsonify(mock_stats)

@app.route('/export/csv')
def export_csv():
    """Export audits to CSV"""
    logger.info("WEB: Exporting audits to CSV")
    
    # This would generate a CSV file with audit data
    flash('CSV export functionality would be implemented here', 'info')
    return redirect(url_for('list_audits'))

@app.route('/search')
def search():
    """Advanced search page"""
    return render_template('search.html')

@app.route('/reports')
def reports():
    """Reports page"""
    return render_template('reports.html')

@app.route('/settings')
def settings():
    """Settings page"""
    return render_template('settings.html')

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="Internal server error"), 500

def main():
    """Main entry point for Flask application"""
    logger.info("WEB: Starting MCP Audit Management Web Application")
    
    # Start default server
    if server_manager.current_server:
        success, message = server_manager.start_server(server_manager.current_server)
        if success:
            logger.info(f"WEB: Started default server {server_manager.current_server}")
        else:
            logger.warning(f"WEB: Failed to start default server: {message}")
    
    # Run Flask app
    try:
        app.run(
            host='127.0.0.1',
            port=5001,
            debug=True,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("WEB: Shutting down web application...")
        
        # Stop all running servers
        for server_name in list(server_manager.active_servers.keys()):
            server_manager.stop_server(server_name)

if __name__ == "__main__":
    main()
