"""Owner: Person A. Hours 1-4.

Load ~60 Florida plants from the EIA-860M Excel file into `sites`.
Download the latest file from https://www.eia.gov/electricity/data/eia860m/ into data/raw/ (git-ignored).
Set geom with ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography, and timezone
'America/Chicago' for sites west of the Apalachicola River (roughly longitude < -85.0).
"""


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
