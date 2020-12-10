import cv2 as cv
import numpy
array_type = type(numpy.array([]))

class Webcam:
    def __init__(self, *cv_conversion_flags, flip=False, swap_axes=False, resolution=()):
        # open webcam
        self.cap = cv.VideoCapture(0, cv.CAP_DSHOW)
        if not self.cap.isOpened() or self.cap.read()[0] is False:
            raise IOError('Failed to read from webcam')
        print('Webcam initialized.')
        # DONE INIT WOO

        if resolution:
            self.cap.set(cv.CAP_PROP_FRAME_WIDTH, resolution[0])
            self.cap.set(cv.CAP_PROP_FRAME_HEIGHT, resolution[1])
        self.width = self.cap.get(cv.CAP_PROP_FRAME_WIDTH)  # float
        self.height = self.cap.get(cv.CAP_PROP_FRAME_HEIGHT)

        self.conversion_flags = cv_conversion_flags # these flags should be any cvtColor() flags (e.g. COLOR_BGR2RGB, etc)
        self.flip = flip # mirror
        self.swap_axes = swap_axes # switches x and y axes, necessary for pygame for unknown reasons

    def read(self):
        frame: array_type = self.cap.read()[1]
        if self.swap_axes:
            frame = frame.swapaxes(0, 1)
        for flag in self.conversion_flags:
            frame = cv.cvtColor(frame, flag)
        if self.flip:
            frame = cv.flip(frame, 0)

        return frame

    def close(self):
        self.cap.release()

    def preview(self, w_name='Webcam Preview'):
        while True:
            cv.imshow(w_name, self.read())

            c = cv.waitKey(1)
            if c == ord('q'):
                break

        self.close()
        cv.destroyAllWindows()


if __name__ == '__main__':
    webcam = Webcam()
    webcam.preview()