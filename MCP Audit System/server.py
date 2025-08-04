#!/usr/bin/env python3
"""
MCP Audit Management System Server
Built using FastMCP v2 framework

This is the main MCP server that provides comprehensive audit management
functionality including CRUD operations, statistics, and AI integration.
"""

import asyncio
import sqlite3
import json
import logging
import argparse
import sys
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from contextlib import asynccontextmanager
from pathlib import Path
import threading
import time
from dataclasses import dataclass
from enum import Enum

# FastMCP v2 imports
from fastmcp import FastMCP
from fastmcp.types import (
    Tool, 
    Resource, 
    Prompt,
    TextContent,
    CallToolRequest,
    GetResourceRequest,
    GetPromptRequest
)

# Setup logging with emoji categorization
class EmojiFormatter(logging.Formatter):
    """Custom formatter that adds emojis for different log levels and operations"""
    
    EMOJI_MAP = {
        'DEBUG': '🔍',
        'INFO': '📝', 
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }
    
    OPERATION_EMOJIS = {
        'database': '🗄️',
        'tool_call': '🔧',
        'resource': '📄',
        'prompt': '💬',
        'server': '🖥️',
        'client': '👤',
        'sql': '📊',
        'performance': '⚡'
    }
    
    def format(self, record):
        # Add emoji based on log level
        level_emoji = self.EMOJI_MAP.get(record.levelname, '📝')
        
        # Add operation emoji based on message content
        message = record.getMessage()
        operation_emoji = ''
        for operation, emoji in self.OPERATION_EMOJIS.items():
            if operation in message.lower():
                operation_emoji = f'{emoji} '
                break
        
        record.msg = f'{level_emoji} {operation_emoji}{record.msg}'
        return super().format(record)

# Setup comprehensive logging
def setup_logging():
    """Setup comprehensive logging system with multiple handlers"""
    logger = logging.getLogger('MCP_AuditServer')
    logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Console handler with emoji formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = EmojiFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    # File handler for detailed logging
    file_handler = logging.FileHandler('mcp_server.log')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = EmojiFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    
    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

class AuditStatus(Enum):
    """Audit status enumeration"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"
    CANCELLED = "cancelled"

@dataclass
class Audit:
    """Audit data class"""
    id: Optional[int] = None
    title: str = ""
    description: str = ""
    date: str = ""
    status: str = AuditStatus.OPEN.value
    assigned_auditor: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert audit to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'date': self.date,
            'status': self.status,
            'assigned_auditor': self.assigned_auditor,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Audit':
        """Create audit from dictionary"""
        return cls(**data)

class DatabaseManager:
    """Comprehensive database manager with connection pooling"""
    
    def __init__(self, db_path: str = "audit_database.db"):
        self.db_path = db_path
        self.connection_pool = []
        self.pool_size = 10
        self.lock = threading.Lock()
        self._initialize_database()
        logger.info(f"Database manager initialized with database at {db_path}")
    
    def _initialize_database(self):
        """Initialize the database with required schema"""
        logger.info("DATABASE: Initializing audit database schema")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create audits table with comprehensive schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    date TEXT,
                    status TEXT DEFAULT 'open',
                    assigned_auditor TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audits_status ON audits(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audits_date ON audits(date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audits_auditor ON audits(assigned_auditor)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audits_created_at ON audits(created_at)')
            
            # Create audit trail table for comprehensive logging
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_trail (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id INTEGER,
                    action TEXT NOT NULL,
                    old_values TEXT,
                    new_values TEXT,
                    user_id TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (audit_id) REFERENCES audits (id)
                )
            ''')
            
            conn.commit()
            logger.info(f"SQL: Database schema created successfully with indexes")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection from pool"""
        conn = None
        try:
            with self.lock:
                if self.connection_pool:
                    conn = self.connection_pool.pop()
                else:
                    conn = sqlite3.connect(self.db_path)
                    conn.row_factory = sqlite3.Row
            
            yield conn
            
        finally:
            if conn:
                with self.lock:
                    if len(self.connection_pool) < self.pool_size:
                        self.connection_pool.append(conn)
                    else:
                        conn.close()
    
    async def create_audit(self, audit: Audit) -> int:
        """Create a new audit record"""
        logger.info(f"DATABASE: Creating new audit with title: {audit.title}")
        
        async with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Set timestamps
            now = datetime.now().isoformat()
            audit.created_at = now
            audit.updated_at = now
            
            cursor.execute('''
                INSERT INTO audits (title, description, date, status, assigned_auditor, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                audit.title,
                audit.description,
                audit.date,
                audit.status,
                audit.assigned_auditor,
                audit.created_at,
                audit.updated_at
            ))
            
            audit_id = cursor.lastrowid
            conn.commit()
            
            # Log to audit trail
            await self._log_audit_trail(conn, audit_id, "CREATE", None, audit.to_dict())
            
            logger.info(f"SQL: Created audit with ID {audit_id}")
            return audit_id
    
    async def get_audit(self, audit_id: int) -> Optional[Audit]:
        """Get audit by ID"""
        logger.debug(f"DATABASE: Retrieving audit with ID {audit_id}")
        
        async with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM audits WHERE id = ?', (audit_id,))
            row = cursor.fetchone()
            
            if row:
                audit_data = dict(row)
                logger.info(f"SQL: Retrieved audit {audit_id}")
                return Audit.from_dict(audit_data)
            
            logger.warning(f"DATABASE: Audit {audit_id} not found")
            return None
    
    async def list_audits(self, filters: Optional[Dict[str, Any]] = None, 
                         limit: int = 100, offset: int = 0) -> List[Audit]:
        """List audits with optional filtering"""
        logger.info(f"DATABASE: Listing audits with filters: {filters}")
        
        async with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build query with filters
            query = "SELECT * FROM audits WHERE 1=1"
            params = []
            
            if filters:
                if 'status' in filters:
                    query += " AND status = ?"
                    params.append(filters['status'])
                
                if 'assigned_auditor' in filters:
                    query += " AND assigned_auditor = ?"
                    params.append(filters['assigned_auditor'])
                
                if 'date_from' in filters:
                    query += " AND date >= ?"
                    params.append(filters['date_from'])
                
                if 'date_to' in filters:
                    query += " AND date <= ?"
                    params.append(filters['date_to'])
                
                if 'search' in filters:
                    query += " AND (title LIKE ? OR description LIKE ?)"
                    search_term = f"%{filters['search']}%"
                    params.extend([search_term, search_term])
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            audits = [Audit.from_dict(dict(row)) for row in rows]
            logger.info(f"SQL: Retrieved {len(audits)} audits")
            return audits
    
    async def update_audit(self, audit_id: int, updates: Dict[str, Any]) -> bool:
        """Update audit with given changes"""
        logger.info(f"DATABASE: Updating audit {audit_id} with changes: {list(updates.keys())}")
        
        # Get current values for audit trail
        old_audit = await self.get_audit(audit_id)
        if not old_audit:
            return False
        
        async with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build update query
            set_clauses = []
            params = []
            
            for key, value in updates.items():
                if key in ['title', 'description', 'date', 'status', 'assigned_auditor']:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)
            
            if not set_clauses:
                logger.warning("DATABASE: No valid fields to update")
                return False
            
            # Always update the updated_at timestamp
            set_clauses.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(audit_id)
            
            query = f"UPDATE audits SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, params)
            
            if cursor.rowcount > 0:
                conn.commit()
                
                # Log to audit trail
                new_audit = await self.get_audit(audit_id)
                await self._log_audit_trail(conn, audit_id, "UPDATE", 
                                          old_audit.to_dict(), new_audit.to_dict())
                
                logger.info(f"SQL: Updated audit {audit_id}")
                return True
            
            logger.warning(f"DATABASE: Failed to update audit {audit_id}")
            return False
    
    async def delete_audit(self, audit_id: int) -> bool:
        """Delete audit by ID"""
        logger.info(f"DATABASE: Deleting audit {audit_id}")
        
        # Get audit for trail before deletion
        old_audit = await self.get_audit(audit_id)
        if not old_audit:
            return False
        
        async with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM audits WHERE id = ?', (audit_id,))
            
            if cursor.rowcount > 0:
                conn.commit()
                
                # Log to audit trail
                await self._log_audit_trail(conn, audit_id, "DELETE", old_audit.to_dict(), None)
                
                logger.info(f"SQL: Deleted audit {audit_id}")
                return True
            
            logger.warning(f"DATABASE: Failed to delete audit {audit_id}")
            return False
    
    async def get_audit_statistics(self) -> Dict[str, Any]:
        """Get comprehensive audit statistics"""
        logger.info("DATABASE: Generating audit statistics")
        
        async with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total audits
            cursor.execute('SELECT COUNT(*) as total FROM audits')
            total = cursor.fetchone()['total']
            
            # Status breakdown
            cursor.execute('''
                SELECT status, COUNT(*) as count 
                FROM audits 
                GROUP BY status
            ''')
            status_breakdown = {row['status']: row['count'] for row in cursor.fetchall()}
            
            # Auditor workload
            cursor.execute('''
                SELECT assigned_auditor, COUNT(*) as count 
                FROM audits 
                WHERE assigned_auditor IS NOT NULL AND assigned_auditor != ''
                GROUP BY assigned_auditor
                ORDER BY count DESC
            ''')
            auditor_workload = {row['assigned_auditor']: row['count'] for row in cursor.fetchall()}
            
            # Recent activity (last 30 days)
            cursor.execute('''
                SELECT COUNT(*) as count 
                FROM audits 
                WHERE created_at >= datetime('now', '-30 days')
            ''')
            recent_audits = cursor.fetchone()['count']
            
            # Monthly trend (last 12 months)
            cursor.execute('''
                SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
                FROM audits 
                WHERE created_at >= datetime('now', '-12 months')
                GROUP BY strftime('%Y-%m', created_at)
                ORDER BY month
            ''')
            monthly_trend = {row['month']: row['count'] for row in cursor.fetchall()}
            
            stats = {
                'total_audits': total,
                'status_breakdown': status_breakdown,
                'auditor_workload': auditor_workload,
                'recent_audits_30_days': recent_audits,
                'monthly_trend': monthly_trend,
                'generated_at': datetime.now().isoformat()
            }
            
            logger.info(f"PERFORMANCE: Generated statistics for {total} audits")
            return stats
    
    async def _log_audit_trail(self, conn, audit_id: int, action: str, 
                              old_values: Optional[Dict], new_values: Optional[Dict]):
        """Log audit trail for comprehensive tracking"""
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO audit_trail (audit_id, action, old_values, new_values, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            audit_id,
            action,
            json.dumps(old_values) if old_values else None,
            json.dumps(new_values) if new_values else None,
            datetime.now().isoformat()
        ))
        conn.commit()

# Initialize database manager
db_manager = DatabaseManager()

# Initialize FastMCP server
mcp = FastMCP("Audit Management System")

# Tool implementations
@mcp.tool()
async def create_audit(
    title: str,
    description: str = "",
    date: str = "",
    status: str = "open",
    assigned_auditor: str = ""
) -> Dict[str, Any]:
    """
    Create a new audit record
    
    Args:
        title: The audit title (required)
        description: Detailed description of the audit
        date: Audit date (ISO format)
        status: Audit status (open, in_progress, completed, closed, cancelled)
        assigned_auditor: Name of the assigned auditor
    
    Returns:
        Dictionary containing the created audit details
    """
    logger.info(f"TOOL_CALL: create_audit - Title: {title}")
    
    try:
        # Validate status
        if status not in [s.value for s in AuditStatus]:
            status = AuditStatus.OPEN.value
        
        # Set default date if not provided
        if not date:
            date = datetime.now().date().isoformat()
        
        audit = Audit(
            title=title,
            description=description,
            date=date,
            status=status,
            assigned_auditor=assigned_auditor
        )
        
        audit_id = await db_manager.create_audit(audit)
        audit.id = audit_id
        
        result = {
            'success': True,
            'audit_id': audit_id,
            'audit': audit.to_dict(),
            'message': f'Audit "{title}" created successfully'
        }
        
        logger.info(f"TOOL_CALL: create_audit completed - ID: {audit_id}")
        return result
        
    except Exception as e:
        logger.error(f"TOOL_CALL: create_audit failed - Error: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to create audit'
        }

@mcp.tool()
async def get_audit(audit_id: int) -> Dict[str, Any]:
    """
    Retrieve a specific audit by ID
    
    Args:
        audit_id: The unique identifier of the audit
    
    Returns:
        Dictionary containing the audit details or error message
    """
    logger.info(f"TOOL_CALL: get_audit - ID: {audit_id}")
    
    try:
        audit = await db_manager.get_audit(audit_id)
        
        if audit:
            result = {
                'success': True,
                'audit': audit.to_dict(),
                'message': f'Audit {audit_id} retrieved successfully'
            }
            logger.info(f"TOOL_CALL: get_audit completed - ID: {audit_id}")
        else:
            result = {
                'success': False,
                'error': 'Audit not found',
                'message': f'Audit {audit_id} does not exist'
            }
            logger.warning(f"TOOL_CALL: get_audit - Audit {audit_id} not found")
        
        return result
        
    except Exception as e:
        logger.error(f"TOOL_CALL: get_audit failed - Error: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to retrieve audit'
        }

@mcp.tool()
async def list_audits(
    status: str = "",
    assigned_auditor: str = "",
    date_from: str = "",
    date_to: str = "",
    search: str = "",
    limit: int = 100,
    offset: int = 0
) -> Dict[str, Any]:
    """
    List audits with optional filtering and pagination
    
    Args:
        status: Filter by audit status
        assigned_auditor: Filter by assigned auditor
        date_from: Filter audits from this date (ISO format)
        date_to: Filter audits to this date (ISO format)
        search: Search in title and description
        limit: Maximum number of results to return
        offset: Number of results to skip for pagination
    
    Returns:
        Dictionary containing list of audits and metadata
    """
    logger.info(f"TOOL_CALL: list_audits - Filters applied")
    
    try:
        # Build filters dictionary
        filters = {}
        if status:
            filters['status'] = status
        if assigned_auditor:
            filters['assigned_auditor'] = assigned_auditor
        if date_from:
            filters['date_from'] = date_from
        if date_to:
            filters['date_to'] = date_to
        if search:
            filters['search'] = search
        
        audits = await db_manager.list_audits(filters, limit, offset)
        
        result = {
            'success': True,
            'audits': [audit.to_dict() for audit in audits],
            'count': len(audits),
            'filters': filters,
            'pagination': {
                'limit': limit,
                'offset': offset
            },
            'message': f'Retrieved {len(audits)} audits'
        }
        
        logger.info(f"TOOL_CALL: list_audits completed - Count: {len(audits)}")
        return result
        
    except Exception as e:
        logger.error(f"TOOL_CALL: list_audits failed - Error: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to list audits'
        }

@mcp.tool()
async def update_audit(audit_id: int, **updates) -> Dict[str, Any]:
    """
    Update an existing audit record
    
    Args:
        audit_id: The unique identifier of the audit to update
        **updates: Key-value pairs of fields to update
    
    Returns:
        Dictionary containing success status and updated audit details
    """
    logger.info(f"TOOL_CALL: update_audit - ID: {audit_id}, Updates: {list(updates.keys())}")
    
    try:
        # Remove audit_id from updates if present
        updates.pop('audit_id', None)
        
        if not updates:
            return {
                'success': False,
                'error': 'No updates provided',
                'message': 'No fields to update'
            }
        
        success = await db_manager.update_audit(audit_id, updates)
        
        if success:
            # Get updated audit
            updated_audit = await db_manager.get_audit(audit_id)
            result = {
                'success': True,
                'audit': updated_audit.to_dict() if updated_audit else None,
                'message': f'Audit {audit_id} updated successfully'
            }
            logger.info(f"TOOL_CALL: update_audit completed - ID: {audit_id}")
        else:
            result = {
                'success': False,
                'error': 'Update failed',
                'message': f'Failed to update audit {audit_id}'
            }
            logger.warning(f"TOOL_CALL: update_audit failed - ID: {audit_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"TOOL_CALL: update_audit failed - Error: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to update audit'
        }

@mcp.tool()
async def delete_audit(audit_id: int) -> Dict[str, Any]:
    """
    Delete an audit record
    
    Args:
        audit_id: The unique identifier of the audit to delete
    
    Returns:
        Dictionary containing success status and confirmation message
    """
    logger.info(f"TOOL_CALL: delete_audit - ID: {audit_id}")
    
    try:
        success = await db_manager.delete_audit(audit_id)
        
        if success:
            result = {
                'success': True,
                'message': f'Audit {audit_id} deleted successfully'
            }
            logger.info(f"TOOL_CALL: delete_audit completed - ID: {audit_id}")
        else:
            result = {
                'success': False,
                'error': 'Deletion failed',
                'message': f'Failed to delete audit {audit_id} (may not exist)'
            }
            logger.warning(f"TOOL_CALL: delete_audit failed - ID: {audit_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"TOOL_CALL: delete_audit failed - Error: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to delete audit'
        }

@mcp.tool()
async def get_audit_statistics() -> Dict[str, Any]:
    """
    Get comprehensive audit statistics and analytics
    
    Returns:
        Dictionary containing various statistics about audits
    """
    logger.info("TOOL_CALL: get_audit_statistics")
    
    try:
        stats = await db_manager.get_audit_statistics()
        
        result = {
            'success': True,
            'statistics': stats,
            'message': 'Statistics generated successfully'
        }
        
        logger.info("TOOL_CALL: get_audit_statistics completed")
        return result
        
    except Exception as e:
        logger.error(f"TOOL_CALL: get_audit_statistics failed - Error: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to generate statistics'
        }

# Resource implementations
@mcp.resource("audit://{id}")
async def get_audit_resource(id: str) -> str:
    """Get audit resource by ID"""
    logger.info(f"RESOURCE: Accessing audit resource - ID: {id}")
    
    try:
        audit_id = int(id)
        audit = await db_manager.get_audit(audit_id)
        
        if audit:
            return json.dumps(audit.to_dict(), indent=2)
        else:
            return json.dumps({'error': f'Audit {id} not found'}, indent=2)
            
    except ValueError:
        return json.dumps({'error': f'Invalid audit ID: {id}'}, indent=2)
    except Exception as e:
        logger.error(f"RESOURCE: Failed to get audit resource - Error: {str(e)}")
        return json.dumps({'error': str(e)}, indent=2)

@mcp.resource("audits://list")
async def get_audits_list_resource() -> str:
    """Get list of all audits as a resource"""
    logger.info("RESOURCE: Accessing audits list resource")
    
    try:
        audits = await db_manager.list_audits()
        audit_list = [audit.to_dict() for audit in audits]
        
        return json.dumps({
            'audits': audit_list,
            'count': len(audit_list),
            'generated_at': datetime.now().isoformat()
        }, indent=2)
        
    except Exception as e:
        logger.error(f"RESOURCE: Failed to get audits list resource - Error: {str(e)}")
        return json.dumps({'error': str(e)}, indent=2)

@mcp.resource("audits://stats")
async def get_audits_stats_resource() -> str:
    """Get audit statistics as a resource"""
    logger.info("RESOURCE: Accessing audits statistics resource")
    
    try:
        stats = await db_manager.get_audit_statistics()
        return json.dumps(stats, indent=2)
        
    except Exception as e:
        logger.error(f"RESOURCE: Failed to get audit statistics resource - Error: {str(e)}")
        return json.dumps({'error': str(e)}, indent=2)

# Prompt implementations
@mcp.prompt("audit_summary_prompt")
async def audit_summary_prompt(audit_id: str = "1") -> str:
    """Generate a prompt for creating audit summaries"""
    logger.info(f"PROMPT: Generating audit summary prompt for ID: {audit_id}")
    
    try:
        audit = await db_manager.get_audit(int(audit_id))
        
        if not audit:
            return f"Error: Audit {audit_id} not found"
        
        prompt = f"""
# Audit Summary Request

Please provide a comprehensive summary for the following audit:

**Audit ID:** {audit.id}
**Title:** {audit.title}
**Description:** {audit.description}
**Current Status:** {audit.status}
**Assigned Auditor:** {audit.assigned_auditor}
**Date:** {audit.date}
**Created:** {audit.created_at}
**Last Updated:** {audit.updated_at}

## Summary Requirements:

1. **Executive Summary** (2-3 sentences)
   - Key findings and overall assessment
   - Risk level and criticality

2. **Key Areas Reviewed**
   - List main areas covered in the audit
   - Highlight any compliance requirements

3. **Findings & Recommendations**
   - Critical issues identified
   - Recommended actions and timeline
   - Risk mitigation strategies

4. **Next Steps**
   - Immediate actions required
   - Follow-up schedule
   - Stakeholder communications

Please format the summary in a professional manner suitable for management review.
        """
        
        return prompt.strip()
        
    except Exception as e:
        logger.error(f"PROMPT: Failed to generate audit summary prompt - Error: {str(e)}")
        return f"Error generating prompt: {str(e)}"

@mcp.prompt("audit_report_prompt")
async def audit_report_prompt(status: str = "all", auditor: str = "all") -> str:
    """Generate a prompt for creating comprehensive audit reports"""
    logger.info(f"PROMPT: Generating audit report prompt - Status: {status}, Auditor: {auditor}")
    
    try:
        # Get filtered audits based on parameters
        filters = {}
        if status != "all":
            filters['status'] = status
        if auditor != "all":
            filters['assigned_auditor'] = auditor
        
        audits = await db_manager.list_audits(filters)
        stats = await db_manager.get_audit_statistics()
        
        prompt = f"""
# Comprehensive Audit Report Generation

Generate a detailed audit report based on the following data:

## Report Parameters:
- **Status Filter:** {status}
- **Auditor Filter:** {auditor}
- **Total Audits in Scope:** {len(audits)}
- **Report Generated:** {datetime.now().isoformat()}

## Overall Statistics:
- **Total Audits in System:** {stats['total_audits']}
- **Recent Activity (30 days):** {stats['recent_audits_30_days']}

### Status Breakdown:
{json.dumps(stats['status_breakdown'], indent=2)}

### Auditor Workload:
{json.dumps(stats['auditor_workload'], indent=2)}

## Audits in Report Scope:
{json.dumps([audit.to_dict() for audit in audits[:10]], indent=2)}
{'... and ' + str(len(audits) - 10) + ' more audits' if len(audits) > 10 else ''}

## Report Requirements:

1. **Executive Dashboard**
   - High-level metrics and KPIs
   - Trend analysis and insights
   - Risk assessment summary

2. **Detailed Analysis**
   - Status distribution analysis
   - Performance by auditor
   - Timeline and completion rates

3. **Risk & Compliance Overview**
   - Critical findings summary
   - Compliance status assessment
   - Risk mitigation progress

4. **Operational Insights**
   - Resource utilization
   - Process improvement opportunities
   - Capacity planning recommendations

5. **Action Items & Follow-up**
   - Outstanding items by priority
   - Recommended next steps
   - Monitoring and review schedule

Please create a comprehensive report that provides actionable insights for management decision-making.
        """
        
        return prompt.strip()
        
    except Exception as e:
        logger.error(f"PROMPT: Failed to generate audit report prompt - Error: {str(e)}")
        return f"Error generating prompt: {str(e)}"

def main():
    """Main entry point for the MCP server"""
    parser = argparse.ArgumentParser(description="MCP Audit Management System Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport method to use"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (for HTTP/SSE transport)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (for HTTP/SSE transport)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Set log level
    logger.setLevel(getattr(logging, args.log_level))
    
    logger.info(f"SERVER: Starting MCP Audit Management System Server")
    logger.info(f"SERVER: Transport: {args.transport}, Host: {args.host}, Port: {args.port}")
    
    try:
        if args.transport == "stdio":
            # Run with stdio transport
            mcp.run_stdio()
        elif args.transport == "http":
            # Run with HTTP transport
            mcp.run_http(host=args.host, port=args.port)
        elif args.transport == "sse":
            # Run with SSE transport
            mcp.run_sse(host=args.host, port=args.port)
        
    except KeyboardInterrupt:
        logger.info("SERVER: Shutting down gracefully...")
    except Exception as e:
        logger.error(f"SERVER: Fatal error - {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
