#!/usr/bin/env python3

import argparse
import csv
import json
import os
import requests

endpoints = {
    "immune_exposure": {
        "url": "https://api.immport.org/data/query/immune_exposure",
        "columns": [
            "subjectAccession",
            "exposureAccession",
            "exposureProcessPreferred",
            "exposureProcessReported",
            "exposureMaterialId",
            "exposureMaterialPreferred",
            "exposureMaterialReported",
            "diseaseOntologyId",
            "diseasePreferred",
            "diseaseReported",
            "diseaseStagePreferred",
            "diseaseStageReported",
        ],
    },
    "fcsAnalyzed": {
        "url": "https://api.immport.org/data/query/result/fcsAnalyzed",
        "columns": [
            "studyAccession",
            "experimentAccession",
            "populationNameReported",
            "populationNamePreferred",
            "populationDefnitionReported",
            "populationDefnitionPreferred",
        ],
    }
}


def fetch_studies():
    pass


def load_studies():
    """Return all HIPC studies as a list of dictionaries."""
    path = "ImmPort_shared_studies_10292020101903_all.txt"
    with open(path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return rows


def load_sids():
    """Return a sorted list of HIPC study IDs."""
    sids = set()
    studies = load_studies()
    for study in studies:
        sids.add(study["study_accession"])
    sids = list(sids)
    sids.sort(key=lambda x : int(x[3:]))
    return sids


def fetch_auth_token():
    """
    Retrieve an authentication token from ImmPort using the given username and password.
    """
    print("Retrieving authentication token from ImmPort ...")

    username = os.environ.get('IMMPORT_USERNAME')
    if not username:
        username = input("IMMPORT_USERNAME not set. Enter ImmPort username: ")
    password = os.environ.get('IMMPORT_PASSWORD')
    if not password:
        password = getpass.getpass('IMMPORT_PASSWORD not set. Enter ImmPort password: ')

    resp = requests.post('https://auth.immport.org/auth/token',
                       data={'username': username, 'password': password})
    if resp.status_code != requests.codes.ok:
        resp.raise_for_status()
    return resp.json()['token']


def fetch_data(auth_token, endpoint, sids=None):
    """Fetch data for a specific endpoint and optional list of study IDs."""
    if endpoint in endpoints:
        url = endpoints[endpoint]["url"]
    else:
        raise Exception(f"Unknown endpoint '{endpoint}'")
    if sids:
        url += "?studyAccession="
        url += ",".join(sids)
    print(url)
    resp = requests.get(url, headers={"Authorization": "bearer " + auth_token})
    if resp.status_code != requests.codes.ok:
        resp.raise_for_status()
    return resp.json()


def fetch(endpoint):
    """Fetch and cache data for all HIPC studies and a given endpoint."""
    auth_token = fetch_auth_token()

    directory = os.path.join("data", endpoint)
    os.makedirs(directory, exist_ok=True)

    sids = load_sids()
    for sid in sids:
        jsonpath = f"{directory}/{sid}.json"
        if os.path.exists(jsonpath):
            continue
        try:
            data = fetch_data(auth_token, endpoint, [sid])
        except Exception:
            auth_token = fetch_auth_token()
            data = fetch_data(auth_token, endpoint, [sid])
        with open(jsonpath, 'w') as f:
            json.dump(data, f, indent=2)


def table(endpoint):
    directory = os.path.join("data", endpoint)
    path = f"{endpoint}.tsv"
    if endpoint in endpoints:
        columns = endpoints[endpoint]["columns"]
    else:
        raise Exception(f"Unknown endpoint '{endpoint}'")
    with open(path, "w") as f:
        w = csv.DictWriter(f, columns, extrasaction="ignore", delimiter="\t", lineterminator="\n")
        w.writeheader()
        for root, dirs, files in os.walk(directory):
            for name in files:
                with open(os.path.join(root, name)) as d:
                    data = json.load(d)
                    if "content" in data:
                        w.writerows(data["content"])
                    elif data:
                        w.writerows(data)


def main():
    parser = argparse.ArgumentParser(description="Fetch HIPC data from ImmPort")
    parser.add_argument("action", choices=["fetch","table"], help="The action: fetch or table")
    parser.add_argument("endpoint", nargs="?", help="The type of data")
    args = parser.parse_args()

    if not args.endpoint:
        print("Available endpoints:")
        for endpoint in endpoints.keys():
            print(f"  {endpoint}")
        return

    if args.action == "fetch":
        fetch(args.endpoint)
    elif args.action == "table":
        table(args.endpoint)
    else:
        raise Exception(f"Unknown action '{action}'")


if __name__ == "__main__":
    main()
