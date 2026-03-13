import json
import requests
from pathlib import Path
import urllib.parse

# ==============================
# CONFIG
# ==============================

SERVER = "http://localhost:8081"

SUBMODEL_ENDPOINT = f"{SERVER}/submodels"
SHELL_ENDPOINT = f"{SERVER}/shells"

SUBMODEL_FOLDER = "./Telefon-Produktion/JSON_Submodels"
SHELL_FOLDER = "./Telefon-Produktion/JSON_Shells"

HEADERS = {"Content-Type": "application/json"}


# ==============================
# HELPER FUNCTIONS
# ==============================

def encode_id(element_id):
    """Encode element ID for use in URL paths"""
    return urllib.parse.quote(element_id, safe='')


def get_existing(endpoint):
    """Hent eksisterende submodels eller shells fra server"""
    r = requests.get(endpoint)
    if not r.ok:
        print(f"Failed to fetch from {endpoint}: {r.status_code}")
        return []
    
    data = r.json()
    # check om result findes
    if "result" in data:
        return [item["id"] for item in data["result"] if "id" in item]
    return []


def delete_existing(endpoint, element_list):
    """Slet eksisterende submodels eller shells"""
    for element_id in element_list:
        try:
            # Encode ID for URL path
            encoded_id = encode_id(element_id)
            r = requests.delete(f"{endpoint}/{encoded_id}")
            if r.ok:
                print(f"✓ Deleted: {element_id}")
            else:
                print(f"✗ Failed to delete {element_id}: {r.status_code}")
        except Exception as e:
            print(f"✗ Error deleting {element_id}: {e}")


def post_json_files(folder, endpoint, skip_duplicates=True):
    """Upload JSON filer fra folder til endpoint"""
    # Find both .json and .JSON files
    json_files = list(Path(folder).rglob("*.json"))
    JSON_files = list(Path(folder).rglob("*.JSON"))
    files = json_files + JSON_files
    
    if not files:
        print(f"No JSON files found in {folder}")
        return

    uploaded = 0
    skipped = 0
    failed = 0

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Ensure required fields are present for submodels
        if "submodels" in endpoint.lower():
            if "modelType" not in data:
                data["modelType"] = "Submodel"
            if "kind" not in data:
                data["kind"] = "Instance"
        
        # Ensure required fields are present for shells
        if "shells" in endpoint.lower():
            if "modelType" not in data:
                data["modelType"] = "AssetAdministrationShell"

        # Try POST first
        r = requests.post(endpoint, json=data, headers=HEADERS)
        
        if r.ok:
            print(f"✓ Uploaded: {file_path.name}")
            uploaded += 1
        elif r.status_code == 409 and skip_duplicates:
            # Element exists and we want to skip duplicates
            print(f"⊘ Already exists: {file_path.name}")
            skipped += 1
        elif r.status_code == 409:
            # Element exists, try to update it instead
            element_id = data.get("id")
            if element_id:
                encoded_id = encode_id(element_id)
                r_put = requests.put(f"{endpoint}/{encoded_id}", json=data, headers=HEADERS)
                if r_put.ok:
                    print(f"↻ Updated: {file_path.name}")
                    uploaded += 1
                else:
                    print(f"✗ Failed to update ({r_put.status_code}): {file_path.name}")
                    failed += 1
            else:
                print(f"✗ Failed (409): {file_path.name} - No ID found in JSON")
                failed += 1
        else:
            print(f"✗ Failed ({r.status_code}): {file_path.name}")
            if r.text:
                # Try to parse error message
                try:
                    error_data = json.loads(r.text) if isinstance(r.text, str) and r.text.startswith('[') else r.text
                    if isinstance(error_data, list) and len(error_data) > 0:
                        print(f"    Error: {error_data[0].get('text', error_data[0])}")
                    else:
                        print(f"    Response: {r.text[:150]}")
                except:
                    print(f"    Response: {r.text[:150]}")
            failed += 1
    
    print(f"\nSummary: {uploaded} uploaded, {skipped} skipped, {failed} failed")


# ==============================
# MAIN
# ==============================

def upload_all(delete_first=False, skip_duplicates=True):
    if delete_first:
        print("=" * 60)
        print("DELETING EXISTING ELEMENTS")
        print("=" * 60)
        print("\nFetching existing Submodels...")
        existing_submodels = get_existing(SUBMODEL_ENDPOINT)
        print(f"Found {len(existing_submodels)} submodels to delete")
        delete_existing(SUBMODEL_ENDPOINT, existing_submodels)

        print("\nFetching existing Shells...")
        existing_shells = get_existing(SHELL_ENDPOINT)
        print(f"Found {len(existing_shells)} shells to delete")
        delete_existing(SHELL_ENDPOINT, existing_shells)

    print("\n" + "=" * 60)
    print("UPLOADING NEW ELEMENTS")
    print("=" * 60)
    print("\nUploading Submodels...")
    post_json_files(SUBMODEL_FOLDER, SUBMODEL_ENDPOINT, skip_duplicates=skip_duplicates)

    print("\nUploading Shells...")
    post_json_files(SHELL_FOLDER, SHELL_ENDPOINT, skip_duplicates=skip_duplicates)


if __name__ == "__main__":
    # Set delete_first=True to delete all existing elements before uploading
    # Set skip_duplicates=False to update existing elements
    upload_all(delete_first=False, skip_duplicates=True)