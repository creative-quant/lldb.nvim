from Queue import Queue

class VimX:
  def __init__(self, vim):
    import logging
    self.logger = logging.getLogger(__name__)
    self.logger.setLevel(logging.INFO)
    self._vim = vim
    self.buffer_cache = {}

  def call(self, *args, **kwargs):
    vim = self._vim
    if 'async' not in kwargs or not kwargs['async']:
      out_q = Queue()
      vim.session.threadsafe_call(lambda:
          out_q.put(vim.call(*args, async=False)))
      return out_q.get()
    else:
      vim.session.threadsafe_call(lambda: vim.call(*args, async=True))

  def eval(self, expr, async=False):
    vim = self._vim
    if not async:
      out_q = Queue()
      vim.session.threadsafe_call(lambda: out_q.put(vim.eval(expr, async=False)))
      return out_q.get()
    else:
      vim.session.threadsafe_call(lambda: vim.eval(expr, async=True))

  def command(self, cmd, async=True):
    vim = self._vim
    vim.session.threadsafe_call(lambda: vim.command(cmd, async=async))

  def log(self, msg, level=1):
    """ Execute echom in vim using appropriate highlighting. """
    level_map = ['None', 'WarningMsg', 'ErrorMsg']
    msg = msg.strip().replace('"', '\\"').replace('\n', '\\n')
    self.command('echohl %s | echom "%s" | echohl None' % (level_map[level], msg))

  def buffer_add(self, name):
    """ Create a buffer (if it doesn't exist) and return its number. """
    bufnr = self.call('bufnr', name, 1)
    self.call('setbufvar', bufnr, '&bl', 1, async=True)
    return bufnr

  def sign_jump(self, bufnr, sign_id):
    """ Try jumping to the specified sign_id in buffer with number bufnr. """
    self.call('lldb#layout#signjump', bufnr, sign_id, async=True)

  def sign_place(self, sign_id, name, bufnr, line):
    """ Place a sign at the specified location. """
    cmd = "sign place %d name=%s line=%d buffer=%s" % (sign_id, name, line, bufnr)
    self.command(cmd)

  def sign_unplace(self, sign_id):
    """ Hide a sign with specified id. """
    self.command("sign unplace %d" % sign_id)

  def map_buffers(self, fn):
    """ Does a map using fn callback on all buffer object and returns a list.
        @param fn: callback function which takes buffer object as a parameter.
                   If None is returned, the item is ignored.
                   If a StopIteration is raised, the loop breaks.
        @return: The last item in the list returned is a placeholder indicating:
                 * completed iteration, if None is present
                 * otherwise, if StopIteration was raised, the message would be the last item
    """
    vim = self._vim
    out_q = Queue(maxsize=1)
    def map_buffers_inner():
      mapped = []
      breaked = False
      for b in vim.buffers:
        try:
          ret = fn(b)
          if ret is not None:
            mapped.append(ret)
        except StopIteration as e:
          mapped.append(e.message)
          breaked = True
          break
      if not breaked:
        mapped.append(None)
      out_q.put(mapped)
    vim.session.threadsafe_call(map_buffers_inner)
    return out_q.get()

  def get_buffer_name(self, nr):
    """ Get the buffer name given its number. """
    def name_mapper(b):
      if b.number == nr:
        raise StopIteration(b.name)
    return self.map_buffers(name_mapper)[0]

  def init_buffers(self):
    """ Create all lldb buffers and initialize the buffer map. """
    buf_map = self.call('lldb#layout#init_buffers')
    return buf_map

  def update_noma_buffer(self, bufnr, content, append=False): # noma => nomodifiable

    def update_mapper(b):
      if b.number == bufnr:
        b.options['ma'] = True
        if append:
          b[-1] += content[0]
          b[:] += content[1:]
          # TODO change cursor pos?
        else:
          b[:] = content
        b.options['ma'] = False
        raise StopIteration

    has_mod = True
    if  not append and bufnr in self.buffer_cache and \
        content.len() == self.buffer_cache[bufnr].len():
      has_mod = False
      for i in range(0, content.len()):
        if content[i] != self.buffer_cache[bufnr][i]:
          has_mod = True
          break

    if has_mod:
      self.map_buffers(update_mapper)
