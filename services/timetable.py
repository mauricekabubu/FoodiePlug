from datetime import date, timedelta


# =========================================================
# TIMETABLE CONSTANTS
# =========================================================

MEAL_TYPES = (
    "breakfast",
    "lunch",
    "supper",
)


# =========================================================
# DATE SERVICES
# =========================================================

def get_week_dates(start_date):
    """
    Return all seven dates starting from start_date.
    """

    return [
        start_date + timedelta(days=day)
        for day in range(7)
    ]


def get_week_start(target_date):
    """
    Return the Monday of the week containing target_date.
    """

    return target_date - timedelta(
        days=target_date.weekday()
    )


def get_week_end(target_date):
    """
    Return the Sunday of the week containing target_date.
    """

    return get_week_start(target_date) + timedelta(days=6)


# =========================================================
# TIMETABLE CREATION
# =========================================================

def create_empty_timetable(start_date):
    """
    Create an empty seven-day timetable.
    """

    dates = get_week_dates(start_date)

    return {
        current_date: {
            meal_type: None
            for meal_type in MEAL_TYPES
        }
        for current_date in dates
    }


# =========================================================
# MEAL ASSIGNMENT
# =========================================================

def assign_meal(
    timetable,
    meal_date,
    meal_type,
    meal
):
    """
    Assign a meal to a specific date and meal type.
    """

    if meal_date not in timetable:
        raise ValueError(
            "Date is not part of the timetable."
        )

    if meal_type not in MEAL_TYPES:
        raise ValueError(
            f"Invalid meal type: {meal_type}"
        )

    if meal is None:
        raise ValueError(
            "Meal cannot be empty."
        )

    timetable[meal_date][meal_type] = meal

    return timetable


# =========================================================
# MEAL REUSE
# =========================================================

def reuse_lunch_for_supper(timetable):
    """
    Reuse lunch as supper when supper has not
    already been assigned.
    """

    for meals in timetable.values():

        lunch = meals.get("lunch")
        supper = meals.get("supper")

        if lunch is not None and supper is None:
            meals["supper"] = lunch

    return timetable


# =========================================================
# REPETITION SERVICES
# =========================================================

def get_scheduled_meals(timetable):
    """
    Return all meals currently scheduled.
    """

    meals = []

    for day in timetable.values():

        for meal in day.values():

            if meal is not None:
                meals.append(meal)

    return meals


def is_meal_already_scheduled(
    timetable,
    meal
):
    """
    Check whether a meal has already been scheduled.
    """

    return meal in get_scheduled_meals(timetable)


def get_meal_frequency(
    timetable,
    meal
):
    """
    Return the number of times a meal appears
    in the timetable.
    """

    return sum(
        1
        for scheduled_meal in get_scheduled_meals(
            timetable
        )
        if scheduled_meal == meal
    )


def get_unused_meals(
    available_meals,
    timetable
):
    """
    Return meals that have not yet been scheduled.
    """

    scheduled = set(
        get_scheduled_meals(timetable)
    )

    return [
        meal
        for meal in available_meals
        if meal not in scheduled
    ]


# =========================================================
# MEAL SELECTION
# =========================================================

def select_meal(
    available_meals,
    timetable,
    allow_repetition=False
):
    """
    Select an appropriate meal.

    If repetition is not allowed, try to select
    a meal that has not already been scheduled.

    If all meals have already been used, repetition
    is allowed as a fallback.
    """

    if not available_meals:
        raise ValueError(
            "No meals are available."
        )

    if allow_repetition:
        return available_meals[0]

    unused_meals = get_unused_meals(
        available_meals,
        timetable
    )

    if unused_meals:
        return unused_meals[0]

    # Fallback:
    # If every meal has already been used,
    # reuse the first available meal.
    return available_meals[0]


# =========================================================
# DAILY TIMETABLE
# =========================================================

def create_daily_timetable(
    meal_options,
    target_date
):
    """
    Create a timetable for one day.

    meal_options example:

    {
        "breakfast": [
            "Tea and eggs",
            "Porridge"
        ],
        "lunch": [
            "Beans and ugali",
            "Rice and beans"
        ],
        "supper": [
            "Chapati and beans",
            "Rice and vegetables"
        ]
    }
    """

    timetable = {
        target_date: {
            "breakfast": None,
            "lunch": None,
            "supper": None,
        }
    }

    for meal_type in MEAL_TYPES:

        options = meal_options.get(
            meal_type,
            []
        )

        if options:
            timetable[target_date][meal_type] = options[0]

    return timetable


# =========================================================
# WEEKLY TIMETABLE
# =========================================================

def create_weekly_timetable(
    meal_options,
    start_date,
    reuse_lunch=True
):
    """
    Generate a seven-day meal timetable.

    The service attempts to avoid unnecessary repetition.

    Lunch can optionally be reused as supper.
    """

    timetable = create_empty_timetable(
        start_date
    )

    dates = get_week_dates(start_date)

    for current_date in dates:

        # ---------------------------------------------
        # BREAKFAST
        # ---------------------------------------------

        breakfast_options = meal_options.get(
            "breakfast",
            []
        )

        if breakfast_options:

            breakfast = select_meal(
                breakfast_options,
                timetable
            )

            assign_meal(
                timetable,
                current_date,
                "breakfast",
                breakfast
            )

        # ---------------------------------------------
        # LUNCH
        # ---------------------------------------------

        lunch_options = meal_options.get(
            "lunch",
            []
        )

        if lunch_options:

            lunch = select_meal(
                lunch_options,
                timetable
            )

            assign_meal(
                timetable,
                current_date,
                "lunch",
                lunch
            )

        # ---------------------------------------------
        # SUPPER
        # ---------------------------------------------

        if reuse_lunch:

            lunch = timetable[
                current_date
            ].get("lunch")

            if lunch is not None:

                assign_meal(
                    timetable,
                    current_date,
                    "supper",
                    lunch
                )

        else:

            supper_options = meal_options.get(
                "supper",
                []
            )

            if supper_options:

                supper = select_meal(
                    supper_options,
                    timetable
                )

                assign_meal(
                    timetable,
                    current_date,
                    "supper",
                    supper
                )

    return timetable


# =========================================================
# TIMETABLE VALIDATION
# =========================================================

def validate_timetable(timetable):
    """
    Validate the structure of a timetable.
    """

    if not timetable:
        raise ValueError(
            "Timetable cannot be empty."
        )

    for meal_date, meals in timetable.items():

        if not isinstance(meal_date, date):
            raise ValueError(
                "Timetable keys must be dates."
            )

        if not isinstance(meals, dict):
            raise ValueError(
                f"Invalid meal structure for "
                f"{meal_date}."
            )

        for meal_type in MEAL_TYPES:

            if meal_type not in meals:
                raise ValueError(
                    f"Missing {meal_type} for "
                    f"{meal_date}."
                )

    return True