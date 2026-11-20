import sqlite3
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(current_dir, 'instance', 'eduagent.db')
if not os.path.exists(db_path):
    db_path = os.path.join(current_dir, 'eduagent.db')

print(f"Checking database at: {db_path}")

def run_migration(admin_usernames):
    if not os.path.exists(db_path):
        print("Error: Database file not found!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        for username in admin_usernames:
            cursor.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
            if cursor.rowcount > 0:
                print(f"✅ Set '{username}' as admin (is_admin = True)")
            else:
                print(f"⚠️  User '{username}' not found in database")

        conn.commit()
        print("Migration completed successfully.")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Grant administrator access to existing users")
    parser.add_argument("usernames", nargs="+")
    run_migration(parser.parse_args().usernames)
