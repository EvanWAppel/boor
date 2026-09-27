"""Authored version-three conversation content. No model calls or random checks."""

QUESTIONS = {
    "road": "What lies ahead in Emberlow?",
    "river": "What should we watch for along the river?",
    "mara": "Why is this delivery important to you?",
}
CHOICES = {
    "town": "Make Emberlow our next stop",
    "river": "Explore the river trail next",
}


def conversation_intro(success: bool) -> str:
    if success:
        return (
            "Mara steadies the rescued cart on the road. The lamps of Emberlow glow ahead, "
            "and there is still time to reach the gate. She turns to you: "
            "'You have my thanks. Before we part, what would you like to know?'"
        )
    return (
        "At Mara's river camp, the rescued crates sit beneath a dry canvas. "
        "Emberlow's gate is closed for the night. Mara pours warm tea: "
        "'We saved the delivery. The town can wait until morning. What would you like to know?'"
    )


def answer_question(topic: str, success: bool) -> str:
    if topic == "road":
        return (
            "'Follow the lamps to the gate. Tell the innkeeper Mara sent you; "
            "she can point you toward a meal and news from the town.'"
            if success
            else "'The gate opens at dawn. Rest here tonight, then tell the innkeeper "
            "Mara sent you. She can point you toward a meal and news from the town.'"
        )
    if topic == "river":
        return (
            "'Keep to the high trail. The lower path floods when the river rises. "
            "The old ferry landing is a good place to start looking around, in daylight.'"
        )
    return (
        "'These crates hold blankets and lamp oil for the riverside homes. "
        "People are counting on them. You helped more than one stranded driver today.'"
    )


def route_ending(choice: str, success: bool) -> str:
    if choice == "town":
        return (
            "You walk beside Mara's cart toward Emberlow and reach the gate before it closes. "
            "With her introduction and your brass river token, you have a friendly first "
            "connection in town."
            if success
            else "You spend a dry night at Mara's camp, "
            "then walk with her cart to Emberlow at dawn. "
            "You arrive later than planned, with a new friend to introduce you to the town."
        )
    return (
        "Mara points out the high river trail before taking her cart toward Emberlow. "
        "You set your sights on the old ferry landing and plan to explore in daylight, "
        "carrying her advice and the brass river token."
        if success
        else "You rest at Mara's camp and make a plan for first light: follow the high river "
        "trail toward the old ferry landing. The delay has given you shelter, a new friend, "
        "and advice about the flooded path."
    )
