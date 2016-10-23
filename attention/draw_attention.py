# draw-like attention
import tensorflow as tf
import numpy as np

def to_att(input, **kwargs):
    if len(input.get_shape()) == 4:
        input = tf.contrib.layers.flatten(input)
    num_inputs = input.get_shape()[1]
    W_init = tf.constant_initializer(np.zeros((num_inputs, 6)))
    b_init = tf.constant_initializer(np.zeros(6))

    return tf.contrib.layers.fully_connected(input, 6,
            activation_fn=None,
            weights_initializer=W_init,
            biases_initializer=b_init, **kwargs)

class AttentionUnit(object):
    def  __init__(self, height, width, num_ch, N):
        self.height = height
        self.width = width
        self.num_ch = num_ch
        self.N = N
        self.read_dim = self.num_ch*self.N*self.N
        self.write_dim = self.num_ch*self.height*self.width

    def get_att_params(self, att, delta_max=None):
        g_x, g_y, log_var, log_delta, log_gamma0, log_gamma1 \
                = tf.split(1, 6, att)
        g_x = 0.5*(self.width+1)*(g_x+1)
        g_y = 0.5*(self.height+1)*(g_y+1)
        sigma = tf.exp(0.5*log_var)

        delta = tf.exp(log_delta)
        if delta_max is not None:
            delta = tf.clip_by_value(delta, 0, delta_max)
        delta = (max(self.height,self.width)-1)*delta/(self.N-1)
        gamma0 = tf.exp(log_gamma0)
        gamma1 = tf.exp(log_gamma1)
        return g_x, g_y, sigma, delta, gamma0, gamma1

    def get_filterbanks(self, g_x, g_y, sigma, delta):
        tol = 1.0e-5
        ind = tf.reshape(tf.cast(tf.range(self.N), tf.float32), [1,-1])
        ind = ind - self.N/2 - 0.5
        mu_x = tf.reshape(g_x + ind*delta, [-1,self.N,1])
        mu_y = tf.reshape(g_y + ind*delta, [-1,self.N,1])
        a = tf.reshape(tf.cast(tf.range(self.width), tf.float32), [1,1,-1])
        b = tf.reshape(tf.cast(tf.range(self.height), tf.float32), [1,1,-1])
        var = tf.reshape(tf.square(sigma), [-1,1,1])
        F_x = tf.exp(-tf.square((a-mu_x))/(2*var))
        F_x = F_x/(tol + tf.reduce_sum(F_x, 2, keep_dims=True))
        F_y = tf.exp(-tf.square((b-mu_y))/(2*var))
        F_y = F_y/(tol + tf.reduce_sum(F_y, 2, keep_dims=True))
        if self.num_ch > 1:
            F_x = tf.tile(F_x, [self.num_ch, 1, 1])
            F_y = tf.tile(F_y, [self.num_ch, 1, 1])
        return F_x, F_y

    def _read(self, x, F_xt, F_y, gamma):
        return tf.reshape(tf.batch_matmul(F_y, tf.batch_matmul(
            tf.reshape(x, [-1,self.height,self.width]), F_xt)),
            [-1,self.read_dim])*tf.reshape(gamma, [-1,1])

    def _write(self, w, F_x, F_y, gamma):
        return tf.reshape(tf.batch_matmul(tf.transpose(F_y, [0,2,1]),
            tf.batch_matmul(tf.reshape(w, [-1,self.N,self.N]), F_x)),
            [-1,self.write_dim])*tf.reshape(1./gamma, [-1,1])

    def read(self, x, att, delta_max=None):
        g_x, g_y, sigma, delta, gamma, _ = \
                self.get_att_params(att, delta_max=delta_max)
        F_x, F_y = self.get_filterbanks(g_x, g_y, sigma, delta)
        F_xt = tf.transpose(F_x, [0,2,1])
        if type(x) is list:
            out = self._read(x[0], F_xt, F_y, gamma)
            for i in range(1, len(x)):
                out = tf.concat(1, [out, self._read(x[i], F_xt, F_y, gamma)])
        else:
            out = self._read(x, F_xt, F_y, gamma)
        return out

    def write(self, w, att, delta_max=None):
        g_x, g_y, sigma, delta, _, gamma = \
                self.get_att_params(att, delta_max=delta_max)
        F_x, F_y = self.get_filterbanks(g_x, g_y, sigma, delta)
        if type(w) is list:
            out = self._write(w[0], F_x, F_y, gamma)
            for i in range(1, len(w)):
                out = tf.concat(1, [out, self._write(w[i], F_x, F_y, gamma)])
        else:
            out = self._write(w, F_x, F_y, gamma)
        return out

if __name__ == '__main__':
    from PIL import Image
    import pylab

    I = Image.open('gong13.jpg')
    width, height = I.size
    I = np.asarray(I, dtype='float32').transpose([2,0,1])
    I = I.reshape((1, 3*height*width))
    I = I / 255.

    N = 100
    unit = AttentionUnit(height, width, 3, N)
    att = tf.placeholder(tf.float32, [1, 6])
    I_read = unit.read(I, att)
    I_write = unit.write(I_read, att)

    def imagify(flat, height, width):
        image = flat.reshape([3, height, width]).transpose([1, 2, 0])
        return image

    sess = tf.Session()
    pylab.figure('original')
    pylab.imshow(imagify(I, height, width))

    pylab.figure('read')
    I_read_run, I_write_run = sess.run([I_read, I_write],
            {att: np.array([[0.0, 0.0, np.log(1.), np.log(0.3),
                np.log(2.), np.log(1.)]])})
    pylab.imshow(imagify(I_read_run, N, N))

    pylab.figure('write')
    pylab.imshow(imagify(I_write_run, height, width))

    pylab.show(block=True)
