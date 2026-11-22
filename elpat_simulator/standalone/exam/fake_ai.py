"""Canned examiner replies for automated tests and offline demos (ELPAT_FAKE_AI=1). Never enable in production."""
import json
import re

_rt_turn = {"n": 0}


def respond(prompt: str) -> str:
    if "Part 1, the warm-up" in prompt:
        return json.dumps({"questions": ["Could you describe your current role in aviation?", "What type of aircraft do you operate?",
                                         "What does a typical working day look like for you?", "What challenges do pilots face during flight operations?"]})
    if "Part 2 (pictures and discussion)" in prompt:
        return json.dumps({"theme": "Helipad operations", "A": {"brief": "A helicopter on a helipad.", "notes": "Normal helipad operation."},
                           "B": {"brief": "Fuel spill on the helipad.", "notes": "Fuel spill hazard."}, "discussion": ["Why is CRM important?", "How do SOPs help?", "What is safety culture?"]})
    if "Part 2, Stage C" in prompt:
        return json.dumps({"answer": "The ground crew had not secured the fuel hose."})
    if "Stage D (aviation discussion)" in prompt:
        return json.dumps({"question": "How can crews keep situational awareness during busy phases of flight?"})
    if "Part 3 listening recording" in prompt:
        title = "Gearbox chip warning" if "Recording 1" in prompt else "Low fuel diversion"
        return json.dumps({"title": title, "setting": "You will hear communications between a helicopter crew and ATC.",
                           "lines": [{"speaker": "NARRATOR", "text": "A helicopter is returning from an offshore platform."},
                                     {"speaker": "PILOT", "text": "Radar, Helicopter two one five, PAN PAN, chip light on the main gearbox."},
                                     {"speaker": "ATC", "text": "Helicopter two one five, roger PAN, turn left heading two seven zero."}],
                           "questions": ["What was the problem?", "Which heading was given?"], "key": ["Main gearbox chip light", "Two seven zero"]})
    if "preparing Part 4" in prompt:
        _rt_turn["n"] = 0
        return json.dumps({"callsign": "Helicopter two one five", "aircraft": "H215", "aerodrome": "Aberdeen", "frequency": "Tower one one eight decimal one",
                           "weather": "wind two four zero, one five knots", "situation": "On the helipad, ready to start.", "first": {"cue": "Request start-up.", "ai": ""}})
    if "RT role-play. React" in prompt:
        _rt_turn["n"] += 1
        n, last = _rt_turn["n"], "LAST exchange" in prompt
        return json.dumps({"check": {"expected": "Full readback with callsign", "ok": n % 2 == 0, "issues": [] if n % 2 == 0 else ["missing callsign"]},
                           "stage": 1 if n < 4 else 2 if n < 8 else 3, "cue": "Chip detector caution on the main gearbox." if n == 5 else "",
                           "ai": "Helicopter two one five, contact Aberdeen Radar one one nine decimal zero five, good day." if last else f"Helicopter two one five, instruction {n}.",
                           "end": last})
    if "ICAO language proficiency rater" in prompt:
        return json.dumps({"criteria": {k: {"level": lv, "reason": "Fake rating for testing."} for k, lv in
                                        [("pronunciation", 4), ("structure", 4), ("vocabulary", 4), ("fluency", 4), ("comprehension", 4), ("interactions", 4)]},
                           "summary": "Test assessment.", "strengths": ["Clear delivery"], "weaknesses": ["Short answers"],
                           "grammar": [], "phraseology": [], "vocabulary": [{"term": "readback", "meaning": "repeating an instruction"}],
                           "suggestions": ["Practise longer answers"], "parts": {"1": "ok", "2": "ok", "3": "ok", "4": "ok"}})
    if re.search(r"Draw this aviation scene", prompt):
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500"><rect width="800" height="500" fill="#7fb2e5"/></svg>'
    return "{}"
