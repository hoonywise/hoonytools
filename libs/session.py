"""
Unified session management for HoonyTools.

Handles credentials, connections, and cleanup for dual schema support (schema1/schema2).
This module merges the previous session.py and dwh_session.py into a single unified system.
"""
import logging
from configparser import ConfigParser
from libs.paths import PROJECT_PATH as BASE_PATH

logger = logging.getLogger(__name__)

# =============================================================================
# Unified Schema Storage
# =============================================================================

schemas = {
    'schema1': {
        'credentials': None,  # {'user': ..., 'password': ..., 'dsn': ..., 'save': bool}
        'label': 'Not Connected',
    },
    'schema2': {
        'credentials': None,
        'label': 'Not Connected',
    }
}

# Last-used credentials for backward compatibility (may be removed in future)
stored_credentials = None


# =============================================================================
# Label Management
# =============================================================================

def get_label(schema):
    """Get display label for a schema pane.
    
    Args:
        schema: 'schema1' or 'schema2'
    
    Returns:
        The label string (username if connected, 'Not Connected' otherwise)
    """
    return schemas.get(schema, {}).get('label', 'Not Connected')


def set_label(schema, label):
    """Set display label for a schema pane.
    
    Args:
        schema: 'schema1' or 'schema2'
        label: The label to display (typically the username)
    """
    if schema in schemas:
        schemas[schema]['label'] = label


# =============================================================================
# Credential Management
# =============================================================================

def get_credentials(schema):
    """Get credentials for a schema.
    
    Args:
        schema: 'schema1' or 'schema2'
    
    Returns:
        Credentials dict or None if not set
    """
    return schemas.get(schema, {}).get('credentials')


def set_credentials(schema, credentials):
    """Set credentials for a schema.
    
    Args:
        schema: 'schema1' or 'schema2'
        credentials: Dict with 'user', 'password', 'dsn', optionally 'save'
    """
    global stored_credentials
    if schema in schemas:
        schemas[schema]['credentials'] = credentials
        # Update label to username when credentials are set
        if credentials and credentials.get('user'):
            schemas[schema]['label'] = credentials['user']
        # Also update stored_credentials for backward compatibility
        stored_credentials = credentials


def clear_credentials(schema):
    """Clear credentials for a schema.
    
    Args:
        schema: 'schema1' or 'schema2'
    """
    if schema in schemas:
        schemas[schema]['credentials'] = None
        schemas[schema]['label'] = 'Not Connected'


# =============================================================================
# Connection Management
# =============================================================================

def register_connection(root, conn, schema):
    """Register a connection object on a window/root for centralized cleanup.
    
    The connection will be closed when cleanup(root, schema) is called.
    
    Args:
        root: The Tkinter root/window to attach the connection to
        conn: The database connection object
        schema: 'schema1' or 'schema2'
    """
    try:
        if root is None or conn is None:
            return
        
        # Get or create the unified connection dict
        db_conns = getattr(root, '_db_conns', None)
        if db_conns is None:
            db_conns = {'schema1': [], 'schema2': []}
            setattr(root, '_db_conns', db_conns)
        
        # Ensure schema key exists
        if schema not in db_conns:
            db_conns[schema] = []
        
        # Avoid duplicate registrations
        if conn not in db_conns[schema]:
            db_conns[schema].append(conn)
            logger.debug(f"Registered connection for {schema} on root={root}")
    except Exception:
        logger.exception(f'Error registering {schema} connection')


def unregister_connection(root, conn, schema):
    """Remove a previously registered connection from the window's registry.
    
    Args:
        root: The Tkinter root/window
        conn: The database connection object to remove
        schema: 'schema1' or 'schema2'
    """
    try:
        if root is None or conn is None:
            return
        
        db_conns = getattr(root, '_db_conns', None)
        if db_conns and schema in db_conns:
            try:
                db_conns[schema].remove(conn)
            except ValueError:
                pass  # Connection not in list
    except Exception:
        logger.exception(f'Error unregistering {schema} connection')


def close_connections(root=None, schema=None):
    """Close registered connections.
    
    Args:
        root: The Tkinter root/window. If None, does nothing.
        schema: 'schema1', 'schema2', or None to close all schemas
    """
    try:
        if root is None:
            return
        
        db_conns = getattr(root, '_db_conns', None)
        if not db_conns:
            return
        
        # Determine which schemas to close
        schemas_to_close = [schema] if schema else ['schema1', 'schema2']
        
        for s in schemas_to_close:
            conns = db_conns.get(s, [])
            logger.debug(f"Closing {len(conns)} connections for {s}")
            for c in conns:
                if c:
                    try:
                        c.close()
                    except Exception:
                        logger.debug(f"Failed closing {s} connection", exc_info=True)
            # Clear the list
            db_conns[s] = []
        
        # Remove the attribute entirely if both are empty
        if not db_conns.get('schema1') and not db_conns.get('schema2'):
            try:
                delattr(root, '_db_conns')
            except Exception:
                pass
    except Exception:
        logger.exception("Error while closing connections")


def clear_unsaved_credentials(schema=None):
    """Clear in-memory credentials when they weren't saved to config.ini.
    
    Args:
        schema: 'schema1', 'schema2', or None to check all schemas
    """
    global stored_credentials
    try:
        cfg = ConfigParser()
        cfg.read(BASE_PATH / "libs" / "config.ini")
        
        schemas_to_check = [schema] if schema else ['schema1', 'schema2']
        
        for s in schemas_to_check:
            if not cfg.has_section(s):
                if s in schemas:
                    schemas[s]['credentials'] = None
                    schemas[s]['label'] = 'Not Connected'
                    logger.debug(f"Cleared in-memory {s} credentials (not saved to config.ini)")
        
        # Clear stored_credentials if no credentials remain
        if not schemas['schema1']['credentials'] and not schemas['schema2']['credentials']:
            stored_credentials = None
    except Exception:
        logger.exception("Failed to clear unsaved credentials")


def cleanup(root=None, schema=None):
    """Perform full session cleanup for the given window/root.
    
    Args:
        root: The Tkinter root/window
        schema: 'schema1', 'schema2', or None to clean all
    """
    close_connections(root, schema)
    clear_unsaved_credentials(schema)


# =============================================================================
# Config.ini Integration
# =============================================================================

def load_saved_credentials():
    """Load saved credentials from config.ini on startup.
    
    Populates schemas dict with any saved credentials.
    """
    global stored_credentials
    try:
        cfg = ConfigParser()
        cfg.read(BASE_PATH / "libs" / "config.ini")
        
        for schema in ['schema1', 'schema2']:
            if cfg.has_section(schema):
                user = cfg.get(schema, 'user', fallback='').strip()
                password = cfg.get(schema, 'password', fallback='').strip()
                dsn = cfg.get(schema, 'dsn', fallback='').strip()
                
                if user:  # Only load if username exists
                    creds = {
                        'user': user,
                        'password': password,
                        'dsn': dsn,
                        'save': True  # Marked as saved since it came from config
                    }
                    schemas[schema]['credentials'] = creds
                    schemas[schema]['label'] = user
                    stored_credentials = creds  # Last loaded becomes stored
                    logger.debug(f"Loaded saved credentials for {schema}: {user}")
    except Exception:
        logger.exception("Failed to load saved credentials from config.ini")


def save_credentials(schema):
    """Save credentials for a schema to config.ini.
    
    Args:
        schema: 'schema1' or 'schema2'
    """
    try:
        creds = schemas.get(schema, {}).get('credentials')
        if not creds:
            return
        
        cfg_path = BASE_PATH / "libs" / "config.ini"
        cfg = ConfigParser()
        cfg.read(cfg_path)
        
        if not cfg.has_section(schema):
            cfg.add_section(schema)
        
        cfg.set(schema, 'user', creds.get('user', ''))
        cfg.set(schema, 'password', creds.get('password', ''))
        cfg.set(schema, 'dsn', creds.get('dsn', ''))
        
        with open(cfg_path, 'w') as f:
            cfg.write(f)
        
        logger.debug(f"Saved credentials for {schema} to config.ini")
    except Exception:
        logger.exception(f"Failed to save {schema} credentials to config.ini")


# =============================================================================
# Pane Label Widget Management (for GUI updates)
# =============================================================================

# References to label widgets for dynamic updates
_label_widgets = {
    'schema1': None,
    'schema2': None
}


def register_label_widget(schema, widget):
    """Register a label widget for a schema pane.
    
    Args:
        schema: 'schema1' or 'schema2'
        widget: The Tkinter Label widget to update
    """
    _label_widgets[schema] = widget


def update_label_widget(schema):
    """Update the label widget for a schema pane with current label value.
    
    Args:
        schema: 'schema1' or 'schema2'
    """
    widget = _label_widgets.get(schema)
    if widget:
        try:
            label = get_label(schema)
            widget.config(text=label)
        except Exception:
            logger.debug(f"Failed to update label widget for {schema}", exc_info=True)
