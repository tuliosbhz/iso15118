from iso15118.shared.messages.enums import UnitSymbol
from iso15118.shared.messages.iso15118_2.datatypes import (
    SAScheduleTuple, PVPMax, PMaxScheduleEntry, RelativeTimeInterval,
    PMaxSchedule, SalesTariff, SalesTariffEntry
)
from typing import List, Optional

def convert_ocpp_to_iso15118_schedule(ocpp_schedule: dict) -> List[SAScheduleTuple]:
    print(ocpp_schedule)
    #charging_profile = ocpp_schedule.get("charging_profile", {})
    profile_id = ocpp_schedule.get("id", 0)
    charging_schedule_list = ocpp_schedule.get("charging_schedule", [])
    print(charging_schedule_list)
    if not charging_schedule_list:
        raise ValueError("OCPP schedule must have at least one charging schedule")

    charging_schedule = charging_schedule_list[0]
    charging_schedule_periods = charging_schedule.get("charging_schedule_period", [])
    duration = charging_schedule.get("duration", 86400)  # Default duration if not provided
    charging_rate_unit = charging_schedule.get("charging_rate_unit", "W")

    if charging_rate_unit not in ["A", "W"]:
        raise ValueError("Unsupported charging rate unit: {}".format(charging_rate_unit))

    def convert_limit_to_pmax(limit, unit):
        if unit == "A":
            return limit * 230  # Assuming a typical voltage of 230V for conversion
        elif unit == "W":
            return limit
        else:
            raise ValueError("Unsupported charging rate unit: {}".format(unit))

    max_start_value = 16777214

    pmax_schedule_entries = [
        PMaxScheduleEntry(
            p_max=PVPMax(
                multiplier=0,
                value=convert_limit_to_pmax(period["limit"], charging_rate_unit),
                unit=UnitSymbol.WATT  # ISO 15118 requires watt as the unit
            ),
            time_interval=RelativeTimeInterval(
                start=min(period["start_period"], max_start_value),
                duration=duration
            )
        ) for period in charging_schedule_periods
    ]

    sales_tariff_entries = [
        SalesTariffEntry(
            e_price_level=1,
            time_interval=RelativeTimeInterval(
                start=min(period["start_period"], max_start_value),
                duration=duration
            )
        ) for period in charging_schedule_periods
    ]

    pmax_schedule = PMaxSchedule(schedule_entries=pmax_schedule_entries)
    sales_tariff = SalesTariff(
        id=f"id{profile_id}",
        sales_tariff_id=profile_id,
        sales_tariff_entry=sales_tariff_entries,
        num_e_price_levels=len(sales_tariff_entries)
    )

    sa_schedule_tuple = SAScheduleTuple(
        sa_schedule_tuple_id=profile_id,
        p_max_schedule=pmax_schedule,
        sales_tariff=sales_tariff
    )

    return sa_schedule_tuple

""" 

# Example OCPP schedule for testing
ocpp_schedule = {
    "chargingProfile": {
        "id": 1,
        "stackLevel": 0,
        "chargingProfilePurpose": "ChargingStationMaxProfile",
        "chargingProfileKind": "Absolute",
        "chargingSchedule": [{
            "id": 0,
            "chargingRateUnit": "A",
            "duration": 10,
            "chargingSchedulePeriod": [
                {"start_period": 1718286909, "limit": 6},
                {"start_period": 1718290509, "limit": 12}
            ]
        }]
    }
}

# Convert and print the result
iso_schedule = convert_ocpp_to_iso15118(ocpp_schedule)

for sa_schedule_tuple in iso_schedule:
    print(vars(sa_schedule_tuple))
    print(vars(sa_schedule_tuple.p_max_schedule))
    for entry in sa_schedule_tuple.p_max_schedule.schedule_entries:
        print(vars(entry))
        print(vars(entry.p_max))
        print(vars(entry.time_interval))
    if sa_schedule_tuple.sales_tariff:
        print(vars(sa_schedule_tuple.sales_tariff))
        for entry in sa_schedule_tuple.sales_tariff.sales_tariff_entry:
            print(vars(entry))
            print(vars(entry.time_interval))

"""