# Solana Monitor 5.2 Hotfix – Duplicate Auth Widgets

Fixes `streamlit.errors.StreamlitDuplicateElementId` caused by rendering the login box in multiple tabs.

Replace in the GitHub root:

- `auth.py`

Then commit/push and reboot Streamlit.
