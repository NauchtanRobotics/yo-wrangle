import os
import shutil
from pathlib import Path
from tempfile import mkstemp
from typing import Optional, List

from yo_ratchet.yo_wrangle.common import YOLO_ANNOTATIONS_FOLDER_NAME
from yo_ratchet.yo_wrangle.wrangle import _get_hits_for_annotations_in_classes
from yo_ratchet.yo_wrangle.aggregated_annotations import (
    filter_and_aggregated_annotations,
    copy_images_and_annotations_listed_in_aggregated_annotations_file,
)


def extract_high_quality_training_data_from_yolo_runs_detect(
    src_images_dir: Path,
    annotations_dir: Path,
    dst_images_dir: Path,
    classes_json_path: Path,
    lower_probability_coefficient: float = 0.7,
    upper_probability_coefficient: Optional[float] = None,
    filter_horizon: float = 0.0,
    y_wedge_apex: float = -0.2,
    classes_to_remove: Optional[List[int]] = None,
    copy_all_src_images: bool = False,
):
    """
    Function to selectively copy images and annotations from a yolov5 detection run.

    This function will copy images from::
        <src_images_dir>/
    to::
        <dst_images_dir>/

    and filtered annotation files from::
        <annotations_dir>/
    to::
        <dst_images_dir>/YOLO_darknet/*

    Filtering bounding box data is enabled according to the following parameters::

        * classes_json_path: Path to a classes information json file which contains
          minimum probability thresholds defined for production usage for each individual
          class. These thresholds are applied to filtering in combination with the parameters
          lower_probability_coefficient and upper_probability_coefficient defined below.

        * lower_probability_coefficient: The minimum probability threshold is this
          coefficient multiplied by the production probability threshold defined for
          each class in class. Choose a value in the range [0-inf]. Higher values
          result in more accurate training data, but too high will result in no training
          data being extracted.

        * upper_probability_coefficient: Set to None to not apply any filtering based
          on an upper limit on confidence, or for selectively mining difficult positives,
          set to a value  lower_probability_coefficient < upper_probability_coefficient < 1

        * filter_horizon: removes objects that have a centre above this normalised
          y-value (range[0-1]). i.e. Only keep objects in the image foreground.

        * wedge_apex: all objects are removed from top-left and top-right corners
          according to a wedge shape. You can choose the position of the apex.
          See docstring TODO: XXXX for more explanation.

        * classes_to_remove: Remove any images that ONLY contain this selection of
          class_ids.

    By default, only images associated with the filtered annotations will be copied to
    dst_images_dir. Optionally, all images in src_images_dir can be copied to dst_images_dir.
    Set copy_all_src_images = True when you wish to increase the weight of hard negatives.

    """
    filtered_detections = filter_and_aggregated_annotations(
        annotations_dir=annotations_dir,
        classes_json_path=classes_json_path,
        output_path=None,
        filter_horizon=filter_horizon,
        y_wedge_apex=y_wedge_apex,
        classes_to_remove=classes_to_remove,
    )

    fd, filtered_annotations_path = mkstemp(suffix=".txt")
    with open(filtered_annotations_path, "w") as fd:
        fd.writelines(filtered_detections)

    copy_images_and_annotations_listed_in_aggregated_annotations_file(
        src_images_dir=src_images_dir,
        filtered_annotations_file=Path(filtered_annotations_path),
        dst_images_dir=dst_images_dir,
        copy_all_src_images=copy_all_src_images,
    )
    os.unlink(filtered_annotations_path)


def selectively_copy_training_data_for_selected_classes(
    classes: List[int],
    src_images_dir: Path,
    dst_images_dir: Path,
    sample_size: Optional[int] = None,
):
    """
    Copies images and their annotations (assumed to be in the ./YOLO_darknet
    sub-folder) to a new location filtering for selected classes. Useful when
    you have to prioritise which classes you need to improve first.

    Not used often because it was easier to just select classes to detect in the
    command for yolov5/detect.py

    Makes a sample folder of image and annotation files from a source directory
    wherein the sample is selected according to a criteria where an annotation
    file includes at least one annotation for a priority class defined by the
    `classes` parameter.

    Assumes images all have '.jpg' extension (lower case).

    NOTE::
        I find it easier to mine by running detect.py with --save-crops --save-txt mode.
        The --conf-thres param can be tweaked to control the sensitivity as required.
        For example, if the model only has 20 instances of a class, set conf-thres to 0.05,
        or if we have >500 instances, set conf-thres = 0.5 or higher.

    I then delete any folders containing defects that I am not seeking (e.g.
    runs/detect/<RUN NAME>/crops/D00).

    Then I use copy_images_recursive_inc_yolo_annotations_by_cropped_image_reference()
    to prepare the sample dataset.
    Set the runs/detect/<RUN NAME> as the reference folder, and set
    `annotations_folder` = "labels".

    """
    dst_annotations_dir = dst_images_dir / YOLO_ANNOTATIONS_FOLDER_NAME
    if dst_annotations_dir.exists():
        raise Exception("Destination folder already exists. Exiting.")
    dst_annotations_dir.mkdir(parents=True)
    src_annotations_dir = src_images_dir / YOLO_ANNOTATIONS_FOLDER_NAME

    hit_list: List[str] = _get_hits_for_annotations_in_classes(
        classes=classes,
        src_images_dir=src_images_dir,
    )
    if sample_size and len(hit_list) > sample_size:
        # Step 1. Wedge filtering.
        pass  # hit_list = get_confident_hits()  # do we really only want the clearest hits?

    for image_name_stem in hit_list:
        src_annotation_path = src_annotations_dir / f"{image_name_stem}.txt"
        dst_annotation_path = dst_annotations_dir / f"{image_name_stem}.txt"
        shutil.copy(src=str(src_annotation_path), dst=str(dst_annotation_path))

        src_image_path = src_images_dir / f"{image_name_stem}.jpg"
        dst_image_path = dst_images_dir / f"{image_name_stem}.jpg"
        shutil.copy(src=str(src_image_path), dst=str(dst_image_path))
