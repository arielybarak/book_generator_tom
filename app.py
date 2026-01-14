import gradio as gr

def debug_echo(json_input):
    # פשוט מחזיר את מה שקיבל כדי לבדוק תקינות
    return {"status": "connected", "received": json_input}

# הגדרת ה-API
iface = gr.Interface(
    fn=debug_echo, 
    inputs=gr.Textbox(label="input"), 
    outputs=gr.JSON()
)

iface.launch()