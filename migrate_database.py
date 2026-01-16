#!/usr/bin/env python3
"""
Database Migration Script for Maxi AI Robot
Upgrades the context_memory.db schema to include new columns and tables.
"""

import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "context_memory.db"


def migrate_database():
    """Migrate database schema to latest version."""
    print("🔧 Starting database migration...")

    if not DB_PATH.exists():
        print("✅ No existing database found. Will be created on first run.")
        return

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Check current schema
        cursor.execute("PRAGMA table_info(conversations)")
        columns = {row[1] for row in cursor.fetchall()}

        migrations_needed = []

        # Migration 1: Add category column to conversations table
        if 'category' not in columns:
            migrations_needed.append("Add 'category' column to conversations")
            cursor.execute("""
                ALTER TABLE conversations 
                ADD COLUMN category TEXT DEFAULT 'general'
            """)
            print("  ✅ Added 'category' column to conversations table")

        # Migration 2: Ensure usage_sessions table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_sessions (
                session_id TEXT PRIMARY KEY,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                mode TEXT NOT NULL,
                questions_count INTEGER DEFAULT 0,
                duration_minutes INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration 3: Ensure daily_statistics table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_statistics (
                date DATE PRIMARY KEY,
                total_sessions INTEGER DEFAULT 0,
                total_questions INTEGER DEFAULT 0,
                total_time_minutes INTEGER DEFAULT 0,
                chat_questions INTEGER DEFAULT 0,
                math_questions INTEGER DEFAULT 0,
                topics_covered TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration 4: Ensure content_filters table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                filter_type TEXT NOT NULL,
                filtered_content TEXT,
                reason TEXT,
                FOREIGN KEY (session_id) REFERENCES usage_sessions(session_id)
            )
        """)

        # Migration 5: Ensure question_logs table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS question_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                question TEXT NOT NULL,
                mode TEXT NOT NULL,
                topic TEXT,
                FOREIGN KEY (session_id) REFERENCES usage_sessions(session_id)
            )
        """)

        # Create indexes if they don't exist
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_date 
            ON usage_sessions(start_time)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_filters_session 
            ON content_filters(session_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_questions_session 
            ON question_logs(session_id)
        """)

        conn.commit()
        conn.close()

        if migrations_needed:
            print(
                f"\n✅ Database migration completed! Applied {len(migrations_needed)} migration(s):")
            for migration in migrations_needed:
                print(f"   - {migration}")
        else:
            print("✅ Database schema is up to date. No migrations needed.")

        print("\n🎉 Database is ready!")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("\n💡 Suggestion: Delete context_memory.db to start fresh:")
        print(f"   rm {DB_PATH}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    migrate_database()
