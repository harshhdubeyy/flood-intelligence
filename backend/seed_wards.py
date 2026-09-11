import asyncio

from geoalchemy2.elements import WKTElement

from backend.models.database import async_session_factory
from backend.models.ward import Ward


async def seed_wards():

    wards_data = [
        {
            "ward_id": "BMC-A",
            "ward_name": "Colaba",
            "city": "Mumbai",
            "area_sqkm": 12.5,
            "population": 180000,
            "is_coastal": True,
            "avg_elevation_m": 8.0,
            "drainage_index": 0.65,

            "geom": "MULTIPOLYGON(((72.8200 18.9000, 72.8400 18.9000, 72.8400 18.9200, 72.8200 18.9200, 72.8200 18.9000)))"
        },

        {
            "ward_id": "BMC-GN",
            "ward_name": "Dharavi",
            "city": "Mumbai",
            "area_sqkm": 2.1,
            "population": 500000,
            "is_coastal": False,
            "avg_elevation_m": 12.0,
            "drainage_index": 0.30,

            "geom": "MULTIPOLYGON(((72.8500 19.0300, 72.8700 19.0300, 72.8700 19.0500, 72.8500 19.0500, 72.8500 19.0300)))"
        },

        {
            "ward_id": "BMC-HW",
            "ward_name": "Bandra West",
            "city": "Mumbai",
            "area_sqkm": 8.5,
            "population": 250000,
            "is_coastal": True,
            "avg_elevation_m": 10.0,
            "drainage_index": 0.55,

            "geom": "MULTIPOLYGON(((72.8200 19.0500, 72.8400 19.0500, 72.8400 19.0700, 72.8200 19.0700, 72.8200 19.0500)))"
        },

        {
            "ward_id": "BMC-L",
            "ward_name": "Kurla",
            "city": "Mumbai",
            "area_sqkm": 15.2,
            "population": 600000,
            "is_coastal": False,
            "avg_elevation_m": 8.0,
            "drainage_index": 0.25,

            "geom": "MULTIPOLYGON(((72.8700 19.0500, 72.9000 19.0500, 72.9000 19.0800, 72.8700 19.0800, 72.8700 19.0500)))"
        },

        {
            "ward_id": "BMC-MW",
            "ward_name": "Chembur",
            "city": "Mumbai",
            "area_sqkm": 18.0,
            "population": 450000,
            "is_coastal": False,
            "avg_elevation_m": 15.0,
            "drainage_index": 0.45,

            "geom": "MULTIPOLYGON(((72.9000 19.0400, 72.9300 19.0400, 72.9300 19.0700, 72.9000 19.0700, 72.9000 19.0400)))"
        }
    ]

    async with async_session_factory() as session:

        for ward_data in wards_data:

            ward = Ward(
                ward_id=ward_data["ward_id"],
                ward_name=ward_data["ward_name"],
                city=ward_data["city"],
                area_sqkm=ward_data["area_sqkm"],
                population=ward_data["population"],
                is_coastal=ward_data["is_coastal"],
                avg_elevation_m=ward_data["avg_elevation_m"],
                drainage_index=ward_data["drainage_index"],

                geom=WKTElement(
                    ward_data["geom"],
                    srid=4326
                )
            )

            session.add(ward)

        await session.commit()

    print("✅ Mumbai ward data seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed_wards())