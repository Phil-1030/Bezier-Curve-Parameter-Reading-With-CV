import cv2
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares

# ==========================================
# Part 1: 基础数学工具
# ==========================================

def cubic_bezier(t, p0, p1, p2, p3):
    """ 计算三次贝塞尔曲线坐标 """
    return ((1-t)**3)[:, None] * p0 + \
           (3*(1-t)**2 * t)[:, None] * p1 + \
           (3*(1-t) * t**2)[:, None] * p2 + \
           (t**3)[:, None] * p3

def fit_cubic_bezier_to_segment(points):
    """
    给定一组点 (N, 2)，固定起点 P0 和终点 P3，
    通过最小二乘法寻找最佳的控制点 P1 和 P2。
    """
    if len(points) < 3:
        # 点太少，退化为直线
        return points[0], points[0], points[-1], points[-1]
    
    p0 = points[0]
    p3 = points[-1]
    
    # 1. 估算每个点在曲线上的 t 值 (0 到 1) - 使用弦长参数化
    dists = np.linalg.norm(points[1:] - points[:-1], axis=1)
    cum_dist = np.cumsum(dists)
    total_len = cum_dist[-1]
    if total_len == 0: return p0, p0, p3, p3
    
    # 这里的 t 是对应每个原始采样点的参数位置
    t_vals = np.concatenate(([0], cum_dist / total_len))
    
    # 2. 定义误差函数：计算预测点和实际点的距离
    def error_func(params):
        # params 包含 p1_x, p1_y, p2_x, p2_y
        curr_p1 = np.array([params[0], params[1]])
        curr_p2 = np.array([params[2], params[3]])
        
        # 计算当前的贝塞尔点
        estimated_points = cubic_bezier(t_vals, p0, curr_p1, curr_p2, p3)
        
        # 返回残差 (x和y方向的差距拉平)
        return (estimated_points - points).ravel()

    # 3. 初始猜测：假设 P1, P2 在 P0-P3 的 1/3 和 2/3 处
    initial_guess = np.concatenate([(2*p0 + p3)/3, (p0 + 2*p3)/3])
    
    # 4. 运行优化
    res = least_squares(error_func, initial_guess)
    
    opt_p1 = np.array([res.x[0], res.x[1]])
    opt_p2 = np.array([res.x[2], res.x[3]])
    
    return p0, opt_p1, opt_p2, p3

# ==========================================
# Part 2: 轮廓分割与拟合流程
# ==========================================

def vectorize_image_bezier(image_path):
    img = cv2.imread(image_path)
    if img is None:
        print("Error: Image not found.")
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # 使用 RETR_TREE 保留层级 (处理孔洞)
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    hierarchy = hierarchy[0] if hierarchy is not None else []
    
    # 设置画板
    fig, ax = plt.subplots(figsize=(12, 12))
    # 显示原图作为背景，增加一点亮度以便观察线条
    ax.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), alpha=0.3)
    
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']

    print(f"开始拟合 {len(contours)} 个轮廓...")

    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        if area < 50: continue 

        # ---------------------------------------------
        # Step A: 寻找角点 (Anchors)
        # ---------------------------------------------
        epsilon = 0.001 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        
        cnt_reshaped = cnt.reshape(-1, 2)
        segment_indices = []
        
        for corner in approx:
            corner_pt = corner[0]
            dists = np.linalg.norm(cnt_reshaped - corner_pt, axis=1)
            idx = np.argmin(dists)
            segment_indices.append(idx)
        
        segment_indices.sort()
        segment_indices.append(segment_indices[0]) 

        # ---------------------------------------------
        # Step B: 对每一段进行贝塞尔拟合
        # ---------------------------------------------
        beziers = []
        
        for k in range(len(segment_indices) - 1):
            start_idx = segment_indices[k]
            end_idx = segment_indices[k+1]
            
            if end_idx > start_idx:
                segment_points = cnt_reshaped[start_idx : end_idx+1]
            else: 
                segment_points = np.vstack((cnt_reshaped[start_idx:], cnt_reshaped[:end_idx+1]))
            
            p0, p1, p2, p3 = fit_cubic_bezier_to_segment(segment_points)
            beziers.append((p0, p1, p2, p3))

        # ---------------------------------------------
        # Step C: 渲染 
        # ---------------------------------------------
        is_hole = (hierarchy[i][3] != -1)
        # 填充颜色：如果是孔洞则用白色，否则轮换颜色
        fill_color = 'white' if is_hole else colors[i % 4]
        # 轮廓线条颜色：醒目的红色 (或者深蓝)，用于强调拟合结果
        stroke_color = '#D62728' if not is_hole else "#5C635C"
        
        all_poly_points = []
        
        for (p0, p1, p2, p3) in beziers:
            # 采样画线
            t = np.linspace(0, 1, 50) # 提高采样率使曲线更平滑
            curve = cubic_bezier(t, p0, p1, p2, p3)
            all_poly_points.append(curve)
            
            # === 绘制贝塞尔曲线实体轮廓 ===
            # zorder=5 保证线在填充之上，但在控制点之下
            ax.plot(curve[:, 0], curve[:, 1], color=stroke_color, linewidth=2.5, zorder=5)

            # === 可视化控制杆 (Handles) ===
            if not is_hole and area > 500:
                # 画 P0 -> P1 的杆 (使用虚线，避免混淆)
                ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color='gray', linestyle='--', lw=0.8, alpha=0.6)
                # 画 P3 -> P2 的杆
                ax.plot([p3[0], p2[0]], [p3[1], p2[1]], color='gray', linestyle='--', lw=0.8, alpha=0.6)
                
                # 画控制点 (P1, P2) - 维持原样
                ax.scatter([p1[0], p2[0]], [p1[1], p2[1]], color='magenta', s=15, zorder=10, edgecolors='white', linewidth=0.5)
                # 画锚点 (P0/P3) - 维持原样
                ax.scatter([p0[0]], [p0[1]], color='black', s=30, marker='s', zorder=11, edgecolors='white', linewidth=0.5)

        # 组合成多边形并填充
        full_curve = np.vstack(all_poly_points)
        # 降低 alpha 值 (0.8 -> 0.3)，让曲线和背景更清晰
        ax.fill(full_curve[:, 0], full_curve[:, 1], color=fill_color, alpha=0.3)

    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title("Vectorized Bezier Contours", fontsize=15)
    
    plt.tight_layout()
    fig.savefig("output5.png", dpi=300, bbox_inches='tight')
    plt.show()
    
    plt.close()

# 运行
vectorize_image_bezier("Barca.png")
