import fitz
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import io
import os
from datetime import datetime

INPUT_PDF = "./files_cash/RC_TO_SIGN.pdf"
OUTPUT_PDF = "./files_cash/signed_RC.pdf"
SIGNATURE_IMG = "signature.png" 

class PDFAnnotator:
    def __init__(self, pdf_path, signature_img):
        if not os.path.exists(pdf_path):
            messagebox.showerror("Error", f"Input PDF not found!\nExpected at: {os.path.abspath(pdf_path)}")
            return
        
        self.signature_img_path = signature_img
        if not os.path.exists(self.signature_img_path):
            # Fallback for old path
            self.signature_img_path = "../kolobok_june_2024/signature.png"
            if not os.path.exists(self.signature_img_path):
                messagebox.showerror("Error", f"Signature image not found!\nExpected at: {os.path.abspath(signature_img)}")
                return

        self.pdf_doc = fitz.open(pdf_path)
        self.current_page_index = 0
        self.zoom = 1.5
        self.signature_coords = None
        self.texts = []

        self.root = tk.Tk(); self.root.title("Guard Angel - PDF Signer"); self.root.geometry("1200x900")
        self.canvas_frame = tk.Frame(self.root); self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.canvas_frame, bg='grey')
        self.v_scroll = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scroll = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y); self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        ctrl_frame = tk.Frame(self.root); ctrl_frame.pack(fill=tk.X)
        tk.Button(ctrl_frame, text="< Prev", command=self.prev_page).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(ctrl_frame, text="Next >", command=self.next_page).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(ctrl_frame, text="Zoom In", command=self.zoom_in).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(ctrl_frame, text="Zoom Out", command=self.zoom_out).pack(side=tk.LEFT, padx=5, pady=5)
        self.input_var = tk.StringVar()
        tk.Label(ctrl_frame, text="Custom Text:").pack(side=tk.LEFT, padx=(20, 0))
        self.input_entry = tk.Entry(ctrl_frame, textvariable=self.input_var, width=30); self.input_entry.pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(ctrl_frame, text="Done & Save", command=self.save_pdf, bg="green", fg="white").pack(side=tk.RIGHT, padx=15, pady=5)
        
        self.click_mode = "signature"
        self.canvas.bind("<Button-1>", self.on_click)
        self.render_pdf()
        self.root.mainloop()

    def render_pdf(self):
        self.canvas.delete("all")
        page = self.pdf_doc[self.current_page_index]
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes()))
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, image=self.tk_img, anchor='nw')
        self.canvas.config(scrollregion=(0, 0, img.width, img.height))
        if self.signature_coords and self.signature_coords[0] == self.current_page_index:
            self.draw_signature_on_canvas(self.signature_coords[1], self.signature_coords[2])
        for pg, txt, (x, y) in self.texts:
            if pg == self.current_page_index: self.draw_text_on_canvas(txt, x, y)

    def draw_signature_on_canvas(self, x, y):
        # **FIX**: Use a fixed size for the preview to avoid blurriness
        sig_img = Image.open(self.signature_img_path).resize((150, 75)) 
        self.tk_sig_img = ImageTk.PhotoImage(sig_img)
        self.canvas.create_image(x, y, image=self.tk_sig_img, anchor='center')

    def draw_text_on_canvas(self, text, x, y):
        self.canvas.create_text(x, y, text=text, fill='blue', font=("Arial", int(12 * self.zoom)))

    def on_click(self, event):
        x = self.canvas.canvasx(event.x); y = self.canvas.canvasy(event.y)
        if self.click_mode == "signature": self.signature_coords = (self.current_page_index, x, y); self.click_mode = "date"
        elif self.click_mode == "date": self.texts.append((self.current_page_index, datetime.now().strftime("%m/%d/%Y"), (x, y))); self.click_mode = "custom"
        elif self.click_mode == "custom":
            custom_text = self.input_var.get().strip()
            if not custom_text: messagebox.showwarning("Missing text", "Please enter text before clicking."); return
            self.texts.append((self.current_page_index, custom_text, (x, y))); self.input_var.set("")
        self.render_pdf()
            
    def save_pdf(self):
        if self.signature_coords:
            pg_idx, x, y = self.signature_coords
            page = self.pdf_doc[pg_idx]; x_pdf = x / self.zoom; y_pdf = y / self.zoom
            img_rect = fitz.Rect(x_pdf - 75, y_pdf - 37.5, x_pdf + 75, y_pdf + 37.5)
            page.insert_image(img_rect, filename=self.signature_img_path)
        for pg_idx, text, (x, y) in self.texts:
            page = self.pdf_doc[pg_idx]; x_pdf = x / self.zoom; y_pdf = y / self.zoom
            page.insert_text(fitz.Point(x_pdf, y_pdf), text, fontsize=11, fontname="helv", color=(0,0,1))
        self.pdf_doc.save(OUTPUT_PDF); self.root.destroy()
        
    def zoom_in(self): self.zoom *= 1.2; self.render_pdf()
    def zoom_out(self): self.zoom /= 1.2; self.render_pdf()
    def next_page(self):
        if self.current_page_index + 1 < len(self.pdf_doc): self.current_page_index += 1; self.render_pdf()
    def prev_page(self):
        if self.current_page_index > 0: self.current_page_index -= 1; self.render_pdf()

if __name__ == "__main__":
    if not os.path.exists('guard_angel'):
        print("Error: This script must be run from the 'guard-angel' project root directory.")
    else: PDFAnnotator(INPUT_PDF, SIGNATURE_IMG)
