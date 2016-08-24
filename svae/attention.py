import tensorflow as tf
import tensorflow.contrib.layers as layers
import numpy as np

# draw-like attention

def linear(x, dim, scope, reuse=False):
    return layers.fully_connected(x, dim,
            scope=scope, reuse=reuse, activation_fn=None)

class AttentionUnit(object):
    def __init__(self, image_shape, N):
        if len(image_shape) == 2:
            self.c = 1
            self.h = image_shape[0]
            self.w = image_shape[1]
        else:
            self.c = image_shape[0]
            self.h = image_shape[1]
            self.w = image_shape[2]
        self.N = N
        self.read_dim = self.c*self.N*self.N
        self.write_dim = self.c*self.h*self.w

    def get_att_params(self, att):
        g_x, g_y, log_var, log_delta, log_gamma = tf.split(1, 5, att)
        g_x = 0.5*(self.w+1)*(g_x+1)
        g_y = 0.5*(self.h+1)*(g_y+1)
        sigma = tf.exp(0.5*log_var)
        delta = (max(self.h,self.w)-1)*tf.exp(log_delta)/(self.N-1)
        gamma = tf.exp(log_gamma)
        return g_x, g_y, sigma, delta, gamma

    def get_filterbanks(self, g_x, g_y, sigma, delta):
        tol = 1.0e-5
        ind = tf.reshape(tf.cast(tf.range(self.N), tf.float32), [1,-1])
        ind = ind - self.N/2 - 0.5
        mu_x = tf.reshape(g_x + ind*delta, [-1,self.N,1])
        mu_y = tf.reshape(g_y + ind*delta, [-1,self.N,1])
        a = tf.reshape(tf.cast(tf.range(self.w), tf.float32), [1,1,-1])
        b = tf.reshape(tf.cast(tf.range(self.h), tf.float32), [1,1,-1])
        var = tf.reshape(tf.square(sigma), [-1,1,1])
        F_x = tf.exp(-tf.square((a-mu_x))/(2*var))
        F_x = F_x/(tol + tf.reduce_sum(F_x, 2, keep_dims=True))
        F_y = tf.exp(-tf.square((b-mu_y))/(2*var))
        F_y = F_y/(tol + tf.reduce_sum(F_y, 2, keep_dims=True))
        if self.c > 1:
            F_x = tf.tile(F_x, [self.c, 1, 1])
            F_y = tf.tile(F_y, [self.c, 1, 1])
        return F_x, F_y

    def read(self, x, hid, scope='read', reuse=False):
        att = linear(hid, 5, scope, reuse=reuse)
        g_x, g_y, sigma, delta, gamma = self.get_att_params(att)
        F_x, F_y = self.get_filterbanks(g_x, g_y, sigma, delta)
        F_xt = tf.transpose(F_x, [0,2,1])
        x_att = tf.reshape(tf.batch_matmul(F_y,
            tf.batch_matmul(tf.reshape(x, [-1,self.h,self.w]), F_xt)),
            [-1,self.read_dim]) * tf.reshape(gamma, [-1,1])
        return x_att

    def read_multiple(self, x, hid, n_read, scope='read', reuse=False):
        x_att = self.read(x, hid, scope=scope+str(0), reuse=reuse)
        for i in range(1, n_read):
            x_att = tf.concat(1, [x_att,
                self.read(x, hid, scope=scope+str(i), reuse=reuse)])
        return x_att

    def write(self, hid, scope='write', reuse=False):
        w = linear(hid, self.read_dim, scope+'_w', reuse=reuse)
        att = linear(hid, 5, scope+'_att', reuse=reuse)
        g_x, g_y, sigma, delta, gamma = self.get_att_params(att)
        F_x, F_y = self.get_filterbanks(g_x, g_y, sigma, delta)
        w_att = tf.reshape(tf.batch_matmul(tf.transpose(F_y, [0,2,1]),
            tf.batch_matmul(tf.reshape(w,[-1,self.N,self.N]), F_x)),
            [-1,self.write_dim]) * tf.reshape(1./gamma, [-1,1])
        return w_att

    def write_multiple(self, hid, n_write, scope='write', reuse=False):
        w_att = self.write(hid, scope=scope+str(0), reuse=reuse)
        for i in range(1, n_write):
            w_att = tf.concat(1, [w_att,
                self.write(hid, scope=scope+str(i), reuse=reuse)])
        return w_att
