import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from pathlib import Path
import google.generativeai as genai

# Configuration
CSV_FILE = "reminders.csv"
API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Streamlit page config
st.set_page_config(
    page_title="NeverMiss Lite",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize session state
if "reminders" not in st.session_state:
    st.session_state.reminders = None
if "parsed_reminder" not in st.session_state:
    st.session_state.parsed_reminder = None
if "api_enabled" not in st.session_state:
    st.session_state.api_enabled = bool(API_KEY)

# Configure Gemini API
if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
    except Exception:
        st.session_state.api_enabled = False

def load_reminders():
    """Load reminders from CSV file."""
    if Path(CSV_FILE).exists():
        return pd.read_csv(CSV_FILE)
    return pd.DataFrame(columns=[
        "reminder_id", "raw_input", "title", "category",
        "date", "time", "priority", "notes", "status", "created_at"
    ])

def save_reminder_to_csv(reminder_data):
    """Save a single reminder to CSV."""
    reminders = load_reminders()
    new_reminder = pd.DataFrame([reminder_data])
    reminders = pd.concat([reminders, new_reminder], ignore_index=True)
    reminders.to_csv(CSV_FILE, index=False)
    st.session_state.reminders = None

def parse_with_gemini(user_input):
    """Send user input to Gemini for parsing."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""You are a reminder parsing assistant. Extract structured information from the user's input about a reminder or appointment.

User input: "{user_input}"

Return ONLY valid JSON (no markdown, no code blocks) with these fields:
- title: A concise title for the reminder (string)
- category: One of 'appointment', 'task', 'opportunity', 'follow-up' (string)
- date: Date in ISO format YYYY-MM-DD if determinable, otherwise null (string or null)
- time: Time in HH:MM format if mentioned, otherwise null (string or null)
- priority: One of 'High', 'Medium', 'Low' (string)
- notes: Any additional details from the input (string)
- confidence: Confidence score 0-1 that the parsing is correct (number)

Handle vague dates intelligently (e.g., "next week" should be estimated from today {datetime.now().strftime('%Y-%m-%d')}).
If the date cannot be determined at all, set to null.
Return ONLY the JSON object, nothing else."""
        
        response = model.generate_content(prompt)
        json_text = response.text.strip()
        
        # Clean up markdown code blocks if present
        if json_text.startswith("```"):
            json_text = json_text.split("```")[1]
            if json_text.startswith("json"):
                json_text = json_text[4:]
            json_text = json_text.strip()
        
        parsed = json.loads(json_text)
        return parsed
    except Exception as e:
        st.error(f"Error calling Gemini API: {str(e)}")
        return None

def is_overdue(date_str):
    """Check if a date is overdue."""
    if not date_str or date_str == "null" or pd.isna(date_str):
        return False
    try:
        reminder_date = datetime.fromisoformat(str(date_str)).date()
        return reminder_date < datetime.now().date()
    except:
        return False

def update_reminder_status(reminder_id, status):
    """Update the status of a reminder."""
    reminders = load_reminders()
    reminders.loc[reminders["reminder_id"] == reminder_id, "status"] = status
    reminders.to_csv(CSV_FILE, index=False)
    st.session_state.reminders = None

# Header
st.title("📋 NeverMiss Lite")
st.markdown("Turn written commitments into follow-through")

# Check API Key
if not st.session_state.api_enabled:
    st.error("🔑 Gemini API key not found. Please set the `GEMINI_API_KEY` environment variable to enable AI features.")

# Main layout with tabs
tab1, tab2 = st.tabs(["Add Reminder", "Dashboard"])

with tab1:
    st.markdown("### 📝 Create a New Reminder")
    
    # Text input
    user_input = st.text_area(
        "Describe your reminder or appointment:",
        placeholder="e.g., Doctor appointment next Thursday at 3pm",
        height=100,
        key="reminder_input",
        disabled=not st.session_state.api_enabled
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        parse_button = st.button("Parse with AI", use_container_width=True, disabled=not st.session_state.api_enabled)
    
    if parse_button and user_input.strip():
        with st.spinner("Analyzing with Gemini..."):
            parsed = parse_with_gemini(user_input)
            if parsed:
                st.session_state.parsed_reminder = parsed
    
    # Display parsed fields if available
    if st.session_state.parsed_reminder:
        st.markdown("### ✅ Review & Edit")
        
        parsed = st.session_state.parsed_reminder
        
        # Show confidence if low
        confidence = parsed.get("confidence", 0.8)
        if confidence < 0.6:
            st.warning(f"⚠️ Low confidence ({confidence:.1%}) in parsing. Please review carefully.")
        
        # Editable fields in columns
        col1, col2 = st.columns(2)
        
        with col1:
            title = st.text_input("Title", value=parsed.get("title", ""))
            category = st.selectbox(
                "Category",
                ["appointment", "task", "opportunity", "follow-up"],
                index=["appointment", "task", "opportunity", "follow-up"].index(parsed.get("category", "task"))
            )
            date = st.text_input(
                "Date (YYYY-MM-DD)",
                value=parsed.get("date") or ""
            )
        
        with col2:
            time = st.text_input(
                "Time (HH:MM, optional)",
                value=parsed.get("time") or ""
            )
            priority = st.selectbox(
                "Priority",
                ["High", "Medium", "Low"],
                index=["High", "Medium", "Low"].index(parsed.get("priority", "Medium"))
            )
        
        notes = st.text_area(
            "Notes",
            value=parsed.get("notes", ""),
            height=80
        )
        
        # Save button
        if st.button("Save Reminder", use_container_width=True, type="primary"):
            if not title.strip():
                st.error("Title is required.")
            else:
                # Generate ID
                reminders = load_reminders()
                reminder_id = len(reminders) + 1
                
                reminder_data = {
                    "reminder_id": reminder_id,
                    "raw_input": user_input,
                    "title": title,
                    "category": category,
                    "date": date if date.strip() else None,
                    "time": time if time.strip() else None,
                    "priority": priority,
                    "status": "pending",
                    "created_at": datetime.now().isoformat()
                }
                
                save_reminder_to_csv(reminder_data)
                st.success("✅ Reminder saved!")
                st.session_state.parsed_reminder = None
                st.session_state.reminders = None
                st.rerun()

with tab2:
    st.markdown("### 📊 Your Reminders")
    
    reminders = load_reminders()
    
    if reminders.empty:
        st.info("No reminders yet. Create one in the 'Add Reminder' tab.")
    else:
        # Sort by date
        reminders_sorted = reminders.copy()
        reminders_sorted["date_sort"] = pd.to_datetime(
            reminders_sorted["date"], errors="coerce"
        )
        reminders_sorted = reminders_sorted.sort_values(
            "date_sort", na_position="last"
        ).drop("date_sort", axis=1)
        
        # Display reminders
        for idx, reminder in reminders_sorted.iterrows():
            is_overdue_flag = is_overdue(reminder["date"])
            is_completed = reminder["status"] == "completed"
            
            # Color-code based on status
            if is_completed:
                st.markdown("---")
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"✓ ~~{reminder['title']}~~ (Completed)")
                with col3:
                    if st.button("Undo", key=f"undo_{reminder['reminder_id']}"):
                        update_reminder_status(reminder["reminder_id"], "pending")
                        st.rerun()
            else:
                if is_overdue_flag:
                    st.markdown(f"### 🔴 {reminder['title']} (OVERDUE)")
                else:
                    st.markdown(f"### {reminder['title']}")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.text(f"📅 {reminder['date'] or 'No date'}")
                with col2:
                    st.text(f"🕐 {reminder['time'] or 'No time'}")
                with col3:
                    priority_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(reminder["priority"], "⚪")
                    st.text(f"{priority_emoji} {reminder['priority']}")
                with col4:
                    st.text(f"📂 {reminder['category']}")
                
                if "notes" in reminder and pd.notna(reminder["notes"]) and reminder["notes"]:
                st.markdown(f"**Notes:** {reminder['notes']}")
                
                st.markdown(f"*Created: {reminder['created_at'][:10]}*")
                
                # Mark as completed button
                if st.button("Mark as Completed", key=f"complete_{reminder['reminder_id']}"):
                    update_reminder_status(reminder["reminder_id"], "pending" if is_completed else "completed")
                    st.rerun()
                
                st.markdown("---")
        
        # Summary stats
        st.markdown("### 📈 Summary")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Reminders", len(reminders))
        with col2:
            st.metric("Pending", len(reminders[reminders["status"] == "pending"]))
        with col3:
            st.metric("Completed", len(reminders[reminders["status"] == "completed"]))
        with col4:
            overdue_count = sum(
                is_overdue(date) and status == "pending"
                for date, status in zip(reminders["date"], reminders["status"])
            )
            st.metric("Overdue", overdue_count)
