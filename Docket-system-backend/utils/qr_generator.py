import qrcode
import io
import base64

def generate_qr(data):
    qr_img = qrcode.make(data)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()
