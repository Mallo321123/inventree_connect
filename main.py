import threading

from auth import auth_job

if __name__ == "__main__":
    auth_thread = threading.Thread(target=auth_job)
    auth_thread.start()
    auth_thread.join()
    print("Auth thread finished")
