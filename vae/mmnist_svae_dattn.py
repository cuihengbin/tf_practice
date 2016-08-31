import tensorflow as tf
from utils.prob import *
from utils.nn import *
from utils.image import batchmat_to_tileimg
from utils.data import load_pkl
from draw.attention import *
import time
import os
import matplotlib.pyplot as plt
import seaborn as sns

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_string('save_dir', '../results/mmnist/svae_dattn',
        """directory to save models.""")
tf.app.flags.DEFINE_integer('n_epochs', 20,
        """number of epochs to run""")
tf.app.flags.DEFINE_integer('n_hid', 600,
        """number of hidden units""")
tf.app.flags.DEFINE_integer('n_lat', 20,
        """number of latent variables""")
tf.app.flags.DEFINE_integer('n_fac', 10,
        """number of factors""")
tf.app.flags.DEFINE_integer('N', 30,
        """attention size""")
tf.app.flags.DEFINE_boolean('train', True,
        """training (True) vs testing (False)""")

if not os.path.isdir(FLAGS.save_dir):
    os.makedirs(FLAGS.save_dir)

n_hid = FLAGS.n_hid
n_lat = FLAGS.n_lat
n_fac = FLAGS.n_fac
height = 60
width = 60
N = FLAGS.N
attunit = AttentionUnit(height, width, 1, N)
n_in = height*width
x = tf.placeholder(tf.float32, shape=[None, n_in])

att_enc = linear(fc(x, 50), 5*n_fac)
x_att = attunit.read_multiple(x, att_enc, n_fac)
hid_enc = fc(tf.concat(1, [att_enc, x_att]), n_hid)
hid_enc = fc(x, n_hid)
z_mean = linear(hid_enc, n_lat)
z_log_var = linear(hid_enc, n_lat)
z = gaussian_sample(z_mean, z_log_var)
w_mean = linear(hid_enc, n_fac)
w_log_var = linear(hid_enc, n_fac)
w = rect_gaussian_sample(w_mean, w_log_var)

hid_dec = fc(z, n_hid)
att_dec = linear(hid_dec, 5*n_fac)
p_att = linear(hid_dec, N*N*n_fac)
factors = attunit.write_multiple(p_att, att_dec, n_fac)
p = tf.slice(w, [0,0], [-1,1])*tf.slice(factors, [0,0], [-1,n_in])
for i in range(1, n_fac):
    p = p + tf.slice(w, [0,i], [-1,1]) * \
            tf.slice(factors, [0,n_in*i], [-1, n_in])
p = tf.nn.sigmoid(p)

train_xy, valid_xy, test_xy = load_pkl('data/mmnist/mmnist.pkl.gz')
train_x, _ = train_xy
valid_x, _ = valid_xy
test_x, _ = test_xy

batch_size = 100
n_train_batches = len(train_x) / batch_size
n_valid_batches = len(valid_x) / batch_size

neg_ll = bernoulli_neg_ll(x, p)
kld_w = rect_gaussian_kld(w_mean, w_log_var, mean0=-1.)
kld_z = gaussian_kld(z_mean, z_log_var)
loss = neg_ll + kld_w + kld_z
train_op = tf.train.AdamOptimizer().minimize(loss)
saver = tf.train.Saver()
sess = tf.Session()

def train():
    logfile = open(FLAGS.save_dir + '/train.log', 'w', 0)
    logfile.write(('n_in: %d, n_hid: %d, n_lat: %d, n_fac: %d\n' \
            % (n_in, n_hid, n_lat, n_fac)))
    sess.run(tf.initialize_all_variables())
    for i in range(FLAGS.n_epochs):
        start = time.time()
        train_neg_ll = 0.
        train_kld_w = 0.
        train_kld_z = 0.
        for j in range(n_train_batches):
            batch_x = train_x[j*batch_size:(j+1)*batch_size]
            _, batch_neg_ll, batch_kld_w, batch_kld_z = \
                    sess.run([train_op, neg_ll, kld_w, kld_z], {x:batch_x})
            train_neg_ll += batch_neg_ll
            train_kld_w += batch_kld_w
            train_kld_z += batch_kld_z
        train_neg_ll /= n_train_batches
        train_kld_w /= n_train_batches
        train_kld_z /= n_train_batches

        valid_neg_ll = 0.
        valid_kld_w = 0.
        valid_kld_z = 0.
        for j in range(n_valid_batches):
            batch_x = valid_x[j*batch_size:(j+1)*batch_size]
            batch_neg_ll, batch_kld_w, batch_kld_z = \
                    sess.run([neg_ll, kld_w, kld_z], {x:batch_x})
            valid_neg_ll += batch_neg_ll
            valid_kld_w += batch_kld_w
            valid_kld_z += batch_kld_z
        valid_neg_ll /= n_valid_batches
        valid_kld_w /= n_valid_batches
        valid_kld_z /= n_valid_batches

        line = "Epoch %d (%f sec), train loss %f = %f + %f + %f, valid loss %f = %f + %f + %f" \
                % (i+1, time.time()-start,
                        train_neg_ll+train_kld_w+train_kld_z,
                        train_neg_ll, train_kld_w, train_kld_z,
                        valid_neg_ll+valid_kld_w+train_kld_z,
                        valid_neg_ll, valid_kld_w, valid_kld_z)
        print line
        logfile.write(line + '\n')
    logfile.close()
    saver.save(sess, FLAGS.save_dir+'/model.ckpt')

def test():
    saver.restore(sess, FLAGS.save_dir+'/model.ckpt')
    batch_x = test_x[0:100]
    fig = plt.figure('original')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(batch_x, (height, width), (10, 10)))
    fig.savefig(FLAGS.save_dir+'/original.png')

    fig = plt.figure('reconstructed')
    plt.gray()
    plt.axis('off')
    p_recon = sess.run(p, {x:batch_x})
    plt.imshow(batchmat_to_tileimg(p_recon, (height, width), (10, 10)))
    fig.savefig(FLAGS.save_dir+'/reconstructed.png')

    batch_w = np.zeros((n_fac*n_fac, n_fac))
    for i in range(n_fac):
        batch_w[i*n_fac:(i+1)*n_fac, i] = 1.0
    batch_z = np.random.normal(size=(n_fac*n_fac, n_lat))
    p_gen = sess.run(p, {w:batch_w, z:batch_z})
    I_gen = batchmat_to_tileimg(p_gen, (height, width), (n_fac, n_fac))
    fig = plt.figure('generated')
    plt.gray()
    plt.axis('off')
    plt.imshow(I_gen)
    fig.savefig(FLAGS.save_dir+'/generated.png')

    """
    fig = plt.figure('factor activation heatmap')
    hist = np.zeros((10, n_fac))
    for i in range(len(test_x)):
        batch_x = test_x[i*batch_size:(i+1)*batch_size]
        batch_w = sess.run(w, {x:batch_x})
        for i in range(batch_size):
            hist[batch_y[i], batch_w[i] > 0] += 1
    sns.heatmap(hist)
    fig.savefig(FLAGS.save_dir+'/feature_activation.png')
    """

    plt.show()

def main(argv=None):
    if FLAGS.train:
        train()
    else:
        test()

if __name__ == '__main__':
    tf.app.run()
