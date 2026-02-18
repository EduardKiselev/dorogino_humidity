import os
import sys
import psycopg2
from dotenv import load_dotenv
import glob

# Load environment variables
load_dotenv()

def connect_to_db():
    """Connect to the PostgreSQL database."""
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'sensor_data'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'password')
    )
    return conn

def apply_migrations():
    """Apply all pending migrations."""
    conn = connect_to_db()
    cursor = conn.cursor()
    
    # Create migrations table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applied_migrations (
            id SERIAL PRIMARY KEY,
            migration_name VARCHAR(255) UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    # Get already applied migrations
    cursor.execute("SELECT migration_name FROM applied_migrations ORDER BY migration_name")
    applied = [row[0] for row in cursor.fetchall()]
    
    # Get all migration files
    migration_files = sorted(glob.glob("/app/migrations/*.sql"))
    
    for migration_file in migration_files:
        migration_name = os.path.basename(migration_file)
        
        if migration_name in applied:
            print(f"Skipping already applied migration: {migration_name}")
            continue
            
        print(f"Applying migration: {migration_name}")
        
        # Read and execute migration
        with open(migration_file, 'r') as f:
            sql_commands = f.read().split(';')
            
        for command in sql_commands:
            command = command.strip()
            if command:
                try:
                    cursor.execute(command)
                except psycopg2.Error as e:
                    print(f"Error executing migration {migration_name}: {e}")
                    conn.rollback()
                    cursor.close()
                    conn.close()
                    sys.exit(1)
        
        # Record that this migration was applied
        cursor.execute(
            "INSERT INTO applied_migrations (migration_name) VALUES (%s)",
            (migration_name,)
        )
        conn.commit()
        print(f"Migration {migration_name} applied successfully")
    
    cursor.close()
    conn.close()
    print("All migrations applied successfully")

def rollback_migration(migration_name):
    """Rollback a specific migration."""
    conn = connect_to_db()
    cursor = conn.cursor()
    
    # Check if migration exists
    cursor.execute("SELECT migration_name FROM applied_migrations WHERE migration_name = %s", (migration_name,))
    result = cursor.fetchone()
    
    if not result:
        print(f"Migration {migration_name} was not applied, nothing to rollback")
        cursor.close()
        conn.close()
        return
    
    # Find the previous migration
    cursor.execute("""
        SELECT migration_name 
        FROM applied_migrations 
        WHERE migration_name < %s 
        ORDER BY migration_name DESC 
        LIMIT 1
    """, (migration_name,))
    prev_migration_result = cursor.fetchone()
    
    if not prev_migration_result:
        print("Cannot rollback first migration")
        cursor.close()
        conn.close()
        return
    
    prev_migration = prev_migration_result[0]
    
    # Look for rollback script
    rollback_file = f"/app/migrations/{migration_name}.rollback.sql"
    if os.path.exists(rollback_file):
        print(f"Rolling back migration: {migration_name}")
        
        with open(rollback_file, 'r') as f:
            sql_commands = f.read().split(';')
            
        for command in sql_commands:
            command = command.strip()
            if command:
                try:
                    cursor.execute(command)
                except psycopg2.Error as e:
                    print(f"Error rolling back migration {migration_name}: {e}")
                    conn.rollback()
                    cursor.close()
                    conn.close()
                    sys.exit(1)
        
        # Remove from applied migrations
        cursor.execute("DELETE FROM applied_migrations WHERE migration_name = %s", (migration_name,))
        conn.commit()
        print(f"Migration {migration_name} rolled back successfully")
    else:
        print(f"No rollback script found for {migration_name}")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrate.py [apply|rollback] [migration_name]")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "apply":
        apply_migrations()
    elif action == "rollback":
        if len(sys.argv) < 3:
            print("Please specify migration name to rollback")
            sys.exit(1)
        rollback_migration(sys.argv[2])
    else:
        print("Unknown action. Use 'apply' or 'rollback'")
        sys.exit(1)