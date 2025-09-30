import sys
import io
import img2pdf
from PyPDF2 import PdfReader, PdfWriter, Transformation

def sign_pdf(input_path, output_path, signature_path):
    """
    A dedicated script to overlay a signature image onto a PDF.
    This is called by the main bot to handle the signing process.
    """
    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        page = reader.pages[0]

        with open(signature_path, "rb") as f:
            signature_pdf_bytes = img2pdf.convert(f.read())
        
        signature_reader = PdfReader(io.BytesIO(signature_pdf_bytes))
        sig_page = signature_reader.pages[0]
        
        # Position signature at bottom-left. You can adjust these values.
        x_pos = 50  # From left edge
        y_pos = 80  # From bottom edge
        scale = 0.3 # How big the signature is

        # Create a transformation and apply it
        op = Transformation().scale(sx=scale, sy=scale).translate(tx=x_pos, ty=y_pos)
        page.merge_transformed_page(sig_page, op, expand=False)

        writer.add_page(page)
        for i in range(1, len(reader.pages)):
            writer.add_page(reader.pages[i])
        
        with open(output_path, "wb") as f:
            writer.write(f)
        
        print("PDF signing successful.")
        return 0
    except Exception as e:
        print(f"Error in sign_rc_helper.py: {e}")
        return 1

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python sign_rc_helper.py <input_pdf> <output_pdf> <signature_png>")
        sys.exit(1)
    
    # Arguments from the command line
    input_pdf = sys.argv[1]
    output_pdf = sys.argv[2]
    signature_png = sys.argv[3]
    
    result_code = sign_pdf(input_pdf, output_pdf, signature_png)
    sys.exit(result_code)
