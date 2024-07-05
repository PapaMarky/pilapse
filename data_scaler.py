class DataScaler:
    def __init__(self, data_limits, view_limits, clamp=False):
        self.data_limits = data_limits
        self.view_limits = view_limits
        self.clamp = clamp

    def update_view_limits(self, view_min, view_max):
        if self.view_limits is None:
            self.view_limits = [None, None]
        if self.view_min is None or view_min < self.view_min:
            self.view_min = view_min
        if self.view_max is None or view_max > self.view_max:
            self.view_max = view_max

    def update_data_limits(self, data_min, data_max):
        if self.data_limits is None:
            self.data_limits = [None, None]
        if self.data_min is None or data_min < self.data_min:
            self.data_min = data_min
        if self.data_max is None or data_max > self.data_max:
            self.data_max = data_max

    def scale(self, data_value):
        data_value = float(data_value)
        if self.clamp:
            if data_value < self.data_min:
                data_value = self.data_min
            elif data_value > self.data_max:
                data_value = self.data_max
        r = (data_value - self.data_min) / (self.data_max - self.data_min)
        return r * (self.view_max - self.view_min) + self.view_min

    @property
    def is_valid(self):
        if self.data_min is None or self.data_max is None or self.view_min is None or self.view_max is None:
            return False
        return True

    @property
    def data_min(self):
        return self.data_limits[0]

    @data_min.setter
    def data_min(self, value):
        self.data_limits[0] = value

    @property
    def data_max(self):
        return self.data_limits[1]

    @data_max.setter
    def data_max(self, value):
        self.data_limits[1] = value

    @property
    def view_min(self):
        return self.view_limits[0]

    @view_min.setter
    def view_min(self, value):
        self.view_limits[0] = value

    @property
    def view_max(self):
        return self.view_limits[1]

    @view_max.setter
    def view_max(self, value):
        self.view_limits[1] = value
