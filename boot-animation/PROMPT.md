# 原头像去背景

工具：内置 imagegen，透明背景编辑模式。

输入：用户提供的 `file_00000000b46c81fa814d8971d43cc42b.png`。
输出：`moze-avatar-cutout.png`。采用原头像，不使用先前重绘版本。

编辑要求：仅去除角色轮廓外的深色背景，变为透明；保留原头像的构图、毛发、配色、黑色椭圆眼睛、耳朵与角，不新增眼睛高光、不重新设计、不补画被画布裁切的部位。角色内部深色区域不能被当成背景去除。

提示词核心：BACKGROUND REMOVAL ONLY. This is a precise cutout edit. Preserve original linework, colours, framing, original plain black oval eyes WITHOUT added highlights. No margin, crop, redraw, or reposition. Do not remove the dark face or eyes; only the outside charcoal background becomes transparent.

生成工具进行了图像编辑；这不是逐像素无损保证。后续程序只缩放并编码此 PNG，供纯黑启动画面显示。
