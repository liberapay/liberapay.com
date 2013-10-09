" To use this file:
"
" Install https://code.google.com/p/lh-vim/source/browse/misc/trunk/plugin/local_vimrc.vim
" which loads `_vimrc_local.vim` files, as well as adding the following lines
" to your `~/.vimrc`:
"     " Use .vimrc_local.vim instead of _vimrc_local.vim
"     let g:local_vimrc = '.vimrc_local.vim'
"
"
" Or, for those who don't wish to set `g:local_vimrc`, you can symlink it to
" `_vimrc_local.vim`:
"     ln -s .vimrc_local.vim _vimrc_local.vim`
"
"
" Note: `_vimrc_local.vim` is ignored in our `.gitignore`, so there shouldn't
" be any issues with you using it

" Expand tabs
setl expandtab

" Use 2-space indentation
setl shiftwidth=2 tabstop=2

" Use 4-space indentation for Python and Simplates
if &filetype == 'python' || bufname("%") =~? '\.spt$'
  setl shiftwidth=4 tabstop=4
endif

" Use 4-width tabs in makefiles, and don't expand tabs
if &filetype == 'make'
  setl noexpandtab shiftwidth=4 tabstop=4
endif

" Make .spt files look like Python
if bufname("%") =~? '\.spt$'
  " Later we can have this `set filetype=aspen` and set an `au FileType aspen`
  " earlier in our rc to load our syntax file (which shouldn't cause problems)
  setl filetype=python
endif
