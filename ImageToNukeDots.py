from PIL import Image, ImageDraw, ImageQt
import os, sys
import PyQt6
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6 import QtWidgets, uic, QtGui, QtCore

ui_file_path = os.path.join(os.path.dirname(__file__), 'ImageToNukeDots.ui')


class ImageToNukeDots(QWidget):
    def __init__(self):
        super().__init__(parent=None)
        self.ui = uic.loadUi(ui_file_path, self)
        self.setWindowTitle('Image To Nuke Dots')
        self.image_path = None
        self.original_pixmap = None
        self.ui.toolButton.released.connect(self.load_image)
        self.ui.convert_button.released.connect(self.convert_image)
        self.ui.slider.valueChanged.connect(self.update_slider)
        self.ui.spinBox.valueChanged.connect(self.update_spinBox)
        self.ui.copy_button.released.connect(self.copy_into_clipboard)

    def resizeEvent(self, event):
        # 4. Trigger re-scaling every time the window/label is resized
        self.update_image_scale()
        super().resizeEvent(event)

    def update_image_scale(self):
        if self.original_pixmap and not self.original_pixmap.isNull():
            # 3. Scale precisely to the label's current width
            # Replace 'image_label' with the objectName of your QLabel in Qt Designer
            scaled = self.original_pixmap.scaled(
                self.image_label.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)
            self.image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

    def update_slider(self, slider_value):
        self.ui.spinBox.setValue(slider_value)
        self.convert_image()
    def update_spinBox(self, spin_value):
        self.ui.slider.setValue(spin_value)
        self.convert_image()


    def load_image(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            # Combined default filter first, followed by specific formats separated by double semicolons (;;)
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;"
            "PNG Files (*.png);;"
            "JPEG Files (*.jpg *.jpeg);;"
            "All Files (*)",
        )
        if file_path:
            self.image_path = file_path
            self.ui.image_path_text.setText(file_path)
            print(f"Selected file: {file_path}")
            self.convert_image()
        else:
            pass

    def create_dotted_image(
        self,
        dots_across=100,
        mode="color",  # Options: 'color' or 'halftone'
        bg_color=(0, 0, 0, 0),  # Transparent background
        scale_factor=1,  # Resolution multiplier
        alpha_threshold=10,  # Skip dots if source pixel alpha is below this
    ):
        """Converts an image into a dotted grid and returns the output image along with a dot matrix."""
        image_path = self.image_path
        img = Image.open(image_path).convert("RGBA")
        orig_w, orig_h = img.size

        aspect_ratio = orig_h / orig_w
        dots_down = int(round(dots_across * aspect_ratio))

        sampled_img = img.resize((dots_across, dots_down), Image.Resampling.LANCZOS)

        cell_size = (orig_w / dots_across) * scale_factor
        out_w = int(dots_across * cell_size)
        out_h = int(dots_down * cell_size)

        output_img = Image.new("RGBA", (out_w, out_h), bg_color)
        draw = ImageDraw.Draw(output_img)

        # Matrix to store structured data: matrix[y][x]
        dot_matrix = []

        for y in range(dots_down):
            row = []
            for x in range(dots_across):
                r, g, b, a = sampled_img.getpixel((x, y))

                # Skip dots on fully transparent areas
                if a < alpha_threshold:
                    row.append(None)
                    continue

                cx = (x + 0.5) * cell_size
                cy = (y + 0.5) * cell_size

                fill_color = None
                radius = 0.0

                if mode == "color":
                    radius = cell_size / 2
                    fill_color = (r, g, b, 255)
                elif mode == "halftone":
                    brightness = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
                    max_radius = cell_size / 2
                    radius = (1.0 - brightness) * max_radius

                    if radius > 0.5:
                        fill_color = (255, 255, 255, 255)

                # Draw dot if it has a valid fill
                if fill_color:
                    draw.ellipse(
                        [cx - radius, cy - radius, cx + radius, cy + radius],
                        fill=fill_color,
                    )

                    row.append(
                        {
                            "grid_pos": (x, y),  # Grid coordinate (col, row)
                            "center": (cx, cy),  # Center pixel position on output canvas
                            "radius": radius,
                            "color": fill_color,  # (R, G, B, A) tuple
                        }
                    )
                else:
                    row.append(None)

            dot_matrix.append(row)

        print(
            f"Done! Created {dots_across}x{dots_down} grid -> ({out_w}x{out_h}px)"
        )
        return [output_img, dot_matrix]

    def create_nuke_script(self, dot_matrix, spacing=12, x_offset=-500, y_offset=100, hide_inputs=True):
        """Converts a dot matrix into a string formatted for pasting directly into Nuke's DAG canvas."""
        nuke_script = ["push $cut_paste_input"]

        # Iterate over the matrix rows and columns
        for row_idx, row in enumerate(dot_matrix):
            for col_idx, dot_data in enumerate(row):
                if dot_data is None:
                    continue

                # Convert RGB tuple (0-255) to Nuke's 32-bit Hex integer color format (0xRRGGBBff)
                r, g, b, _ = dot_data["color"]
                hex_color = f"0x{r:02x}{g:02x}{b:02x}ff"

                # Calculate DAG positioning
                dag_x = x_offset + (col_idx * spacing)
                dag_y = y_offset + (row_idx * spacing)

                dot_name = f"Dot_grid_{col_idx}_{row_idx}"

                # Format individual Dot node entry
                nuke_script.append(f"Dot {{")
                nuke_script.append(f" inputs 0")
                nuke_script.append(f" name {dot_name}")
                nuke_script.append(f" tile_color {hex_color}")
                nuke_script.append(f" selected true")
                nuke_script.append(f" xpos {dag_x}")
                nuke_script.append(f" ypos {dag_y}")
                if hide_inputs:
                    nuke_script.append(f" hide_input true")
                nuke_script.append(f"}}\n")

        full_nuke_text = "\n".join(nuke_script)

        return full_nuke_text

    
    def convert_image(self):
        if self.image_path:
            data = self.create_dotted_image(
                dots_across=self.ui.slider.value(),
            )
            pil_image = data[0]
            dot_matrix = data[1]

            qimage = ImageQt.ImageQt(pil_image)
            pixmap = QtGui.QPixmap.fromImage(qimage)
            self.original_pixmap = pixmap
            self.update_image_scale()

            nuke_text = self.create_nuke_script(dot_matrix)
            self.ui.nuke_text.setText(nuke_text)


    def copy_into_clipboard(self):
        text = self.ui.nuke_text.toPlainText()
        clipboard = QtGui.QGuiApplication.clipboard()
        clipboard.setText(text)






#set cut_paste_input [stack 0]
#push $cut_paste_input
#Dot {
# name Dot1
# selected true
# xpos -532
# ypos 115
#}
#Dot {
# inputs 0
# name Dot2
# selected true
# xpos -520
# ypos 115
#}












if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = ImageToNukeDots()
    window.show()
    sys.exit(app.exec())


    