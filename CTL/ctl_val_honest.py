from CTL.causal_tree import *


class HonestValidationNode(Node):

    def __init__(self, var=0.0, **kwargs):
        super().__init__(**kwargs)

        self.var = var


# ----------------------------------------------------------------
# Honest = validation causal tree (binary, base objective with honest penalty, no estimation set)
# ----------------------------------------------------------------
class CausalTreeLearnHonestValidation(CausalTree):

    # ----------------------------------------------------------------
    # TODO: Not sure if I should estimate only with validation set???
    # ----------------------------------------------------------------

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root = HonestValidationNode()
        self.train_to_est_ratio = 1.0

        self.num_samples = 1.0
        self.num_treated = 1.0
        self.treated_share = 1.0

    def fit(self, x, y, t):
        if x.shape[0] == 0:
            return 0

        # ----------------------------------------------------------------
        # Seed
        # ----------------------------------------------------------------
        np.random.seed(self.seed)

        # ----------------------------------------------------------------
        # Verbosity?
        # ----------------------------------------------------------------

        # ----------------------------------------------------------------
        # Split data
        # ----------------------------------------------------------------
        train_x, val_x, train_y, val_y, train_t, val_t = train_test_split(x, y, t, random_state=self.seed, shuffle=True,
                                                                          test_size=self.val_split)

        num_treat, _ = get_treat_size(t)
        self.num_treated = num_treat
        self.num_samples = x.shape[0]
        self.treated_share = self.num_treated / self.num_samples
        # ----------------------------------------------------------------
        # effect and pvals
        # ----------------------------------------------------------------
        # TODO: val est?
        _, effect = tau_squared(y, t)
        p_val = get_pval(y, t)
        self.root.effect = effect
        self.root.p_val = p_val

        self.train_to_est_ratio = val_x.shape[0] / train_x.shape[0]
        current_var_treat, current_var_control = variance(train_y, train_t)
        num_treat, num_cont = get_treat_size(train_t)
        # current_var = (1 * self.train_to_est_ratio) * (
        #         (current_var_treat / num_treat) + (current_var_control / num_cont))
        current_var = (1 * self.train_to_est_ratio) * (
                (current_var_treat / self.treated_share) + (current_var_control / (1 - self.treated_share)))

        self.root.var = current_var
        # ----------------------------------------------------------------
        # Not sure if i should eval in root or not
        # ----------------------------------------------------------------
        eval, mse = self._eval(train_y, train_t, val_y, val_t)
        self.root.obj = eval - current_var

        # ----------------------------------------------------------------
        # Add control/treatment means
        # ----------------------------------------------------------------
        self.root.control_mean = np.mean(val_y[val_t == 0])
        self.root.treatment_mean = np.mean(val_y[val_t == 1])

        self.root.num_samples = x.shape[0]

        self._fit(self.root, train_x, train_y, train_t, val_x, val_y, val_t)

    def _fit(self, node: HonestValidationNode, train_x, train_y, train_t, val_x, val_y, val_t):

        if train_x.shape[0] == 0 or val_x.shape[0] == 0:
            return node

        if node.node_depth > self.tree_depth:
            self.tree_depth = node.node_depth

        if self.max_depth == self.tree_depth:
            self.num_leaves += 1
            node.leaf_num = self.num_leaves
            node.is_leaf = True
            return node

        best_gain = 0.0
        best_attributes = []
        best_tb_obj, best_fb_obj = (0.0, 0.0)
        best_tb_var, best_fb_var = (0.0, 0.0)

        column_count = train_x.shape[0]
        for col in range(0, column_count):
            unique_vals = np.unique(train_x[:, col])

            # ----------------------------------------------------------------
            # TODO: Max values stuff
            # ----------------------------------------------------------------

            for value in unique_vals:

                (val_x1, val_x2, val_y1, val_y2, val_t1, val_t2) \
                    = divide_set(val_x, val_y, val_t, col, value)

                # check validation size
                val_size = self.val_split * self.min_size if self.val_split * self.min_size > 2 else 2
                val_nt1, val_nc1, val_check1 = min_size_value_bool(val_size, val_t1)
                val_nt2, val_nc2, val_check2 = min_size_value_bool(val_size, val_t2)
                if val_check1 or val_check2:
                    continue

                # check training size
                (train_x1, train_x2, train_y1, train_y2, train_t1, train_t2) \
                    = divide_set(train_x, train_y, train_t, col, value)
                train_nt1, train_nc1, train_check1 = min_size_value_bool(self.min_size, train_t1)
                train_nt2, train_nc2, train_check2 = min_size_value_bool(self.min_size, train_t2)
                if train_check1 or train_check2:
                    continue

                # ----------------------------------------------------------------
                # Honest penalty
                # ----------------------------------------------------------------
                var_treat1, var_control1 = variance(train_y1, train_t1)
                var_treat2, var_control2 = variance(train_y2, train_t2)
                # tb_var = (1 + self.train_to_est_ratio) * (
                #         (var_treat1 / (train_nt1 + 1)) + (var_control1 / (train_nc1 + 1)))
                # fb_var = (1 + self.train_to_est_ratio) * (
                #         (var_treat2 / (train_nt2 + 1)) + (var_control2 / (train_nc2 + 1)))
                tb_var = (1 + self.train_to_est_ratio) * (
                        (var_treat1 / self.treated_share) + (var_control1 / (1 - self.treated_share)))
                fb_var = (1 + self.train_to_est_ratio) * (
                        (var_treat2 / self.treated_share) + (var_control2 / (1 - self.treated_share)))

                # ----------------------------------------------------------------
                # Regular objective
                # ----------------------------------------------------------------
                tb_eval, tb_mse = self._eval(train_y1, train_t1, val_y1, val_t1)
                fb_eval, fb_mse = self._eval(train_y2, train_t2, val_y2, val_t2)

                # combine honest and our objective
                split_eval = (tb_eval + fb_eval) - (tb_var + fb_var)
                gain = -(node.obj - node.var) + split_eval

                if gain > best_gain:
                    best_gain = gain
                    best_attributes = [col, value]
                    best_tb_obj, best_fb_obj = (tb_eval, fb_eval)
                    best_tb_var, best_fb_var = (tb_var, fb_var)

            if best_gain > 0:
                node.col = best_attributes[0]
                node.value = best_attributes[1]

                (train_x1, train_x2, train_y1, train_y2, train_t1, train_t2) \
                    = divide_set(train_x, train_y, train_t, node.col, node.value)

                (val_x1, val_x2, val_y1, val_y2, val_t1, val_t2) \
                    = divide_set(val_x, val_y, val_t, node.col, node.value)

                # ----------------------------------------------------------------
                # TODO: same note as at the top (not sure if sep val est)
                # ----------------------------------------------------------------
                y1 = np.concatenate((train_y1, val_y1))
                y2 = np.concatenate((train_y2, val_y2))
                t1 = np.concatenate((train_t1, val_t1))
                t2 = np.concatenate((train_t2, val_t2))

                best_tb_effect = ace(y1, t1)
                best_fb_effect = ace(y2, t2)
                tb_p_val = get_pval(y1, t1)
                fb_p_val = get_pval(y2, t2)

                self.obj = self.obj - (node.obj - node.var) + (best_tb_obj + best_fb_obj -
                                                               best_tb_var - best_fb_var)
                # ----------------------------------------------------------------
                # Ignore "mse" here, come back to it later?
                # ----------------------------------------------------------------

                tb = HonestValidationNode(obj=best_tb_obj, effect=best_tb_effect, p_val=tb_p_val,
                                          node_depth=node.node_depth + 1,
                                          var=best_tb_var, num_samples=y1.shape[0])
                fb = HonestValidationNode(obj=best_fb_obj, effect=best_fb_effect, p_val=fb_p_val,
                                          node_depth=node.node_depth + 1,
                                          var=best_tb_var, num_samples=y2.shape[0])

                node.true_branch = self._fit(tb, train_x1, train_y1, train_t1, val_x1, val_y1, val_t1)
                node.false_branch = self._fit(fb, train_x2, train_y2, train_t2, val_x2, val_y2, val_t2)

                if node.effect > self.max_effect:
                    self.max_effect = node.effect
                else:
                    self.min_effect = node.effect

                return node

            else:
                if node.effect > self.max_effect:
                    self.max_effect = node.effect
                if node.effect < self.min_effect:
                    self.min_effect = node.effect

                self.num_leaves += 1
                node.leaf_num = self.num_leaves
                node.is_leaf = True
                return node

    def _eval(self, train_y, train_t, val_y, val_t):
        total_train = train_y.shape[0]
        total_val = val_y.shape[0]

        return_val = (-np.inf, -np.inf)

        if total_train == 0 or total_val == 0:
            return return_val

        train_effect = ace(train_y, train_t)
        val_effect = ace(val_y, val_t)

        train_mse = (1 - self.weight) * total_train * (train_effect ** 2)
        cost = self.weight * total_val * np.abs(train_effect - val_effect)

        obj = (train_mse - cost) / (np.abs(total_train - total_val) + 1)
        mse = total_train * (train_effect ** 2)

        return obj, mse
