import numpy as np
import pandas
from cv2 import cv2
from pathlib import Path
from sys import platform
from typing import List, Optional, Tuple

from cv2.cv2 import VideoWriter_fourcc

from yo_wrangle.common import get_all_jpg_recursive, get_id_to_label_map


def draw_polygon_on_image(
        image_file: str,
        coords: List[List[float]],
        dst_path: Path = None,
        class_name: Optional[str] = None,
):
    """
    This function takes a copy of an image and draws a bounding box
    (polygon) according to the provided `coords` parameter.

    If a `dst_path` is provided, the resulting image will be saved.
    Otherwise, the image will be displayed in a pop up window.

    """
    image = cv2.imread(image_file)
    height, width, channels = image.shape

    polygon_1 = [[x * width, y * height] for x, y in coords]
    polygon_1 = np.array(polygon_1, np.int32).reshape((-1, 1, 2))
    is_closed = True
    thickness = 2
    cv2.polylines(image, [polygon_1], is_closed, (0, 255, 0), thickness)
    if class_name:
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(image, class_name, (200, 500), font, 4, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(image, class_name, (203, 503), font, 4, (0, 0, 0), 2, cv2.LINE_AA)
    if dst_path:
        cv2.imwrite(str(dst_path), image)
    else:
        cv2.imshow("Un-transformed Bounding Box", image)
        cv2.waitKey()
        cv2.destroyAllWindows()


def save_bounding_boxes_on_images(
        images_root: Path,
        dst_root: Path,
        ai_file_path: Path,
        class_list_path: Path,
):
    """
    Save a copy of all images from images_root to dst_root with bounding boxes applied.
    Only one bounding box is drawn on each image in dst_root.  Filenames in dst_root
    include an index for the defect number.

    If more than one defect was found in an image, there will be multiple corresponding
    images in dst_root.

    """
    df = pandas.read_csv(
        filepath_or_buffer=ai_file_path,
        header=None,
        sep=" ",
        usecols=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        names=[
            "Photo_Name",
            "Class_ID",
            "x1",
            "y1",
            "x2",
            "y2",
            "x3",
            "y3",
            "x4",
            "y4",
        ],
    )
    images_with_defects = df["Photo_Name"].unique()
    print("\nCount images with defects = ", len(images_with_defects))
    assert dst_root.exists() is False, "Destination directory already exists"
    dst_root.mkdir(parents=True)

    id_to_class_name_map = get_id_to_label_map(class_name_list_path=class_list_path)

    for img_path in get_all_jpg_recursive(img_root=images_root):
        photo_name = img_path.name
        image_data = df.loc[df["Photo_Name"] == photo_name].reset_index()
        if len(image_data) == 0:
            continue
        for index, row in image_data.iterrows():
            class_id = row["Class_ID"]
            # if int(class_id) in [7, 10]:
            #     continue
            class_name = id_to_class_name_map[class_id]
            series = row[
                [
                    "x1",
                    "y1",
                    "x2",
                    "y2",
                    "x3",
                    "y3",
                    "x4",
                    "y4",
                ]
            ]
            bounding_box_coords = [
                [series["x1"], series["y1"]],
                [series["x2"], series["y2"]],
                [series["x3"], series["y3"]],
                [series["x4"], series["y4"]],
            ]
            dst_path = dst_root / f"{img_path.stem}_{img_path.suffix}"
            if index == 0:
                image_filename = str(img_path)
            else:
                image_filename = str(dst_path)

            draw_polygon_on_image(
                image_file=image_filename,
                coords=bounding_box_coords,
                dst_path=dst_path,
                class_name=class_name
            )


def _crop_image_for_given_centre(
    img: np.ndarray,
    dim: Tuple[int, int],
    y_centre: float = 0.5,  # for centre_crop y_centre = 0.5
):
    """
    Returns center cropped image unless the centre_crop parameter is set
    to False, in which case cropping removes the image foreground.

    Args:
    img: image to be center cropped
    dim: dimensions (width, height) to be cropped

    """
    width, height = img.shape[1], img.shape[0]

    crop_width = dim[0] if dim[0] < img.shape[1] else img.shape[1]
    crop_height = dim[1] if dim[1] < img.shape[0] else img.shape[0]

    min_x = int(width / 2.0 - crop_width / 2.0)
    max_x = int(width / 2.0 + crop_width / 2.0)

    min_y = int(height * y_centre - crop_height / 2.0)
    if min_y < 0:
        print("min_y is less than 0")
        min_y = 0
    max_y = min_y + crop_height

    if max_y > height:
        print("max_y is greater than image height")
        max_y = height
        min_y = max_y - crop_height

    crop_img = img[min_y:max_y, min_x:max_x]
    return crop_img


def _scale_image(img: np.ndarray, factor: float):
    """Returns resize image by scale factor.
    This helps to retain resolution ratio while resizing.
    Args:
    img: image to be scaled
    factor: scale factor to resize
    """
    return cv2.resize(img, (int(img.shape[1] * factor), int(img.shape[0] * factor)))


def zoom_image(
    zoom_pcnt: float,
    image: np.ndarray,
    y_centre: float = 0.5,
) -> np.ndarray:
    """
    Return an image that is 'zoomed': same size as the original provided,
    but which has undergone a resize and centre crop.

    Usage::

        `zoom_image(zoom_pcnt=90.0, image=image)`

    will return an image for which the features are approximately 10% larger
    except those features which are near the edge of the image which may
    be partially removed.

    """
    width, height = image.shape[1], image.shape[0]
    factor = 100 / zoom_pcnt
    image = _scale_image(img=image, factor=factor)

    image = _crop_image_for_given_centre(img=image, dim=(width, height), y_centre=y_centre)
    return image


def make_movie_adding_intermediate_progressive_zooms(
    img_root: Path,
    y_centre: float = 0.5,
):
    """
    For each of the images in a directory, 2 additional images that can help
    create a transition effect when creating a video from the still images.

    Applies resize and centre crop to give a progressive zooming into end of
    road at the x = 0.5, y = 0.5.  This works great if the horizon of the image
    is at the centre of the image.

    """
    done_once = False
    for img_path in get_all_jpg_recursive(img_root=img_root):

        image = cv2.imread(filename=str(img_path))
        image_small = _scale_image(img=image, factor=0.3)
        if not done_once:
            frame_size = (image_small.shape[1], image_small.shape[0])
            dst_file = img_root / "an_output_video.mp4"
            out = cv2.VideoWriter(str(dst_file), VideoWriter_fourcc(*'mp4v'), 52, frame_size)
            done_once = True

        out.write(image=image_small)
        for i in range(20):
            image = zoom_image(zoom_pcnt=99.5, image=image, y_centre=y_centre)
            image_small = _scale_image(img=image, factor=0.3)
            out.write(image=image_small)


def test_make_avi_movie():
    make_movie_adding_intermediate_progressive_zooms(
        img_root=Path("C:\\test", y_centre=0.49)
    )
