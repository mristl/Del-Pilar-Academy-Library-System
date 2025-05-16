import os
import django
import time
from django.core.management import call_command
from django.conf import settings # To ensure settings are configured



def main():
    # Point to your project's settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finalproject.settings') # REPLACE your_project_name
    
    # Configure Django settings
    if not settings.configured:
        django.setup()

    print("Scheduler started. Press Ctrl+C to stop.")
    interval_seconds = 60  # Run every 60 seconds (1 minute) - Adjust as needed

    try:
        while True:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Running send_overdue_notifications command...")
            try:
                call_command('check_overdue') # Name of your management command
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Command finished.")
            except Exception as e:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error running command: {e}")
            
            print(f"Waiting for {interval_seconds} seconds...")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("Scheduler stopped by user.")

if __name__ == '__main__':
    main()