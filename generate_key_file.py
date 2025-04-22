import secrets
import os

# --- Configuration ---
OUTPUT_FILENAME = "auth_key.txt"
TOKEN_LENGTH_BYTES = 16 # Creates a 32-character hex token
# --- End Configuration ---

def generate_local_auth_file():
    """Generates a secure token and writes it to the specified file locally."""
    try:
        # Generate a cryptographically strong random token
        master_key = secrets.token_hex(TOKEN_LENGTH_BYTES)

        # Get the directory where this script is located
        script_dir = os.path.dirname(__file__)
        file_path = os.path.join(script_dir, OUTPUT_FILENAME)

        # Write the token to the file (overwrites if exists)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(master_key)

        print(f"Successfully generated '{OUTPUT_FILENAME}' in the script directory.")
        print("-" * 30)
        print(f"IMPORTANT: Copy the following key into your config.ini under [Settings] as ExpectedAuthKey:")
        print(master_key)
        print("-" * 30)

    except IOError as e:
        print(f"ERROR: Could not write file '{file_path}'. Error: {e}")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {e}")

if __name__ == "__main__":
    generate_local_auth_file()